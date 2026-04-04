import base64
import hashlib
import subprocess
import os
import logging

class CryptoError(Exception):
    pass

def parse_asn1(data: bytes):
    """Parses basic ASN.1 structures recursively. Returns a list of parsed elements."""
    parsed = []
    i = 0
    while i < len(data):
        try:
            tag = data[i]
            i += 1
            
            # Length decoding
            length = data[i]
            i += 1
            if length & 0x80:
                num_bytes = length & 0x7F
                length = int.from_bytes(data[i:i+num_bytes], 'big')
                i += num_bytes
                
            value = data[i:i+length]
            i += length
            
            if tag in (0x30, 0x04):  # Sequence or Octet String (unwrap)
                try:
                    parsed_sub = parse_asn1(value)
                    # For Octet String wrapping a Sequence, we might get a single nested list
                    if tag == 0x04 and len(parsed_sub) == 1 and isinstance(parsed_sub[0], list):
                        parsed.append(parsed_sub[0])
                    else:
                        parsed.append(parsed_sub)
                except Exception:
                    parsed.append(value)
            elif tag == 0x02:  # Integer
                parsed.append(int.from_bytes(value, 'big'))
            elif tag == 0x03:  # Bit String
                # Skip the first byte (padding bits number)
                try:
                    parsed.append(parse_asn1(value[1:]))
                except Exception:
                    parsed.append(value)
            else:
                parsed.append(value)
        except IndexError:
            break
            
    return parsed

def get_rsa_components(pem_data: str):
    """Extracts modulus (n) and private exponent (d) from a PEM PKCS8 or PKCS1 structure."""
    lines = pem_data.strip().splitlines()
    b64_data = "".join([l for l in lines if not l.startswith("-----")])
    try:
        der_data = base64.b64decode(b64_data)
    except Exception as e:
        raise CryptoError(f"Failed to decode PEM base64: {e}")
    
    parsed = parse_asn1(der_data)
    
    # PKCS#1 RSA private key structure: Sequence of [version, n, e, d, p, q, dmp1, dmq1, iqmp]
    def find_rsa_ints(item):
        if isinstance(item, list):
            # Evaluate if this constitutes the internal component structures (9 ints)
            if len(item) == 9 and all(isinstance(x, int) for x in item):
                return item[1], item[3]  # n, d
            for sub in item:
                res = find_rsa_ints(sub)
                if res:
                    return res
        return None
        
    res = find_rsa_ints(parsed)
    if not res:
        raise CryptoError("Could not mathematically extract RSA structures from the decrypted PEM")
    return res

def emsa_pkcs1_v1_5_encode(msg: bytes, em_len: int) -> bytes:
    h = hashlib.sha256(msg).digest()
    # Standard DigestInfo structure prefix defining SHA-256 context
    t = b'\x30\x31\x30\x0d\x06\x09\x60\x86\x48\x01\x65\x03\x04\x02\x01\x05\x00\x04\x20' + h
    if em_len < len(t) + 11:
        raise CryptoError("Intended encoded message length too short")
    ps = b'\xff' * (em_len - len(t) - 3)
    return b'\x00\x01' + ps + b'\x00' + t

def sign_pure_python(payload: bytes, private_key_pem: str) -> bytes:
    n, d = get_rsa_components(private_key_pem)
    
    n_len = (n.bit_length() + 7) // 8
    em = emsa_pkcs1_v1_5_encode(payload, n_len)
    
    m = int.from_bytes(em, 'big')
    # Execution: math.pow modulo
    s = pow(m, d, n)
    
    return s.to_bytes(n_len, 'big')

def sign_openssl(payload: bytes, private_key_pem: str) -> bytes:
    import shutil
    
    openssl_exe = shutil.which("openssl")
    if not openssl_exe and os.path.exists("C:\\Program Files\\Git\\usr\\bin\\openssl.exe"):
        openssl_exe = "C:\\Program Files\\Git\\usr\\bin\\openssl.exe"
        
    if not openssl_exe:
        raise FileNotFoundError("openssl missing")
    
    # Pipe the private key via stdin to avoid writing secrets to disk.
    # OpenSSL reads the key from fd 3 via the engine /dev/fd/3 on Linux,
    # but on Windows this isn't available. We use a two-step approach:
    # 1. Feed both key and payload through a single subprocess call using stdin.
    # We use "-sign /dev/stdin" with the key passed via a process substitution,
    # but the simplest cross-platform approach is to still use a temp file
    # with restricted permissions and immediate cleanup.
    import tempfile
    
    # Create with restricted permissions from the start (not world-readable)
    fd = os.open(
        os.path.join(tempfile.gettempdir(), f"backup_rsa_{os.getpid()}.tmp"),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600
    )
    key_path = os.path.join(tempfile.gettempdir(), f"backup_rsa_{os.getpid()}.tmp")
    try:
        os.write(fd, private_key_pem.encode("utf-8"))
        os.close(fd)
        
        result = subprocess.run(
            [openssl_exe, "dgst", "-sha256", "-sign", key_path],
            input=payload,
            capture_output=True,
            check=True
        )
        return result.stdout
    finally:
        if os.path.exists(key_path):
            os.remove(key_path)

def sign_rsa_sha256(payload: bytes, private_key_pem: str, force_pure_python: bool = False) -> bytes:
    logger = logging.getLogger("backup")
    
    if force_pure_python:
        logger.debug("Forcing Pure-Python RSA signing as specifically requested by config.")
        return sign_pure_python(payload, private_key_pem)
        
    try:
        return sign_openssl(payload, private_key_pem)
    except FileNotFoundError:
        logger.warning("'openssl' subprocess binary not found! Successfully falling back to built-in Pure-Python RSA implementation.")
        return sign_pure_python(payload, private_key_pem)
    except subprocess.CalledProcessError as e:
        logger.warning(f"OpenSSL execution failed with error: {e.stderr.decode() if e.stderr else e}. Falling back to Pure-Python RSA.")
        return sign_pure_python(payload, private_key_pem)
