import hmac
import hashlib
import datetime
import urllib.parse

def sign(key, msg):
    """Generates an HMAC SHA-256 signature."""
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

def get_signature_key(key, date_stamp, region_name, service_name):
    """Calculates the AWS Signature Version 4 signing key."""
    k_date = sign(('AWS4' + key).encode('utf-8'), date_stamp)
    k_region = sign(k_date, region_name)
    k_service = sign(k_region, service_name)
    k_signing = sign(k_service, 'aws4_request')
    return k_signing

def generate_signed_headers(method: str, host: str, uri: str, query: str, 
                            access_key: str, secret_key: str, region: str, service: str, 
                            payload_hash: str, headers: dict) -> dict:
    """
    Generates all headers needed for an authenticated AWS SigV4 request.
    `headers` should contain user-provided headers including x-amz-date and x-amz-content-sha256 if needed.
    """
    # Create a copy of headers so we don't mutate the original
    final_headers = {k.lower(): v for k, v in headers.items()}
    final_headers['host'] = host
    
    if 'x-amz-date' not in final_headers:
        # Require amz-date to be present or passed.
        # usually timestamp string: 20260404T061800Z
        now = datetime.datetime.now(datetime.timezone.utc)
        final_headers['x-amz-date'] = now.strftime('%Y%m%dT%H%M%SZ')
        
    amz_date = final_headers['x-amz-date']
    date_stamp = amz_date[:8] # YYYYMMDD
    
    # 1. Create canonical headers and signed headers
    header_keys = sorted(final_headers.keys())
    canonical_headers = ""
    signed_headers_list = []
    
    for k in header_keys:
        k_lower = k.lower()
        signed_headers_list.append(k_lower)
        # Strip trailing/leading spaces inside values
        val = str(final_headers[k]).strip()
        canonical_headers += f"{k_lower}:{val}\n"
        
    signed_headers = ';'.join(signed_headers_list)
    
    # Encode URI according to RFC 3986, except S3 doesn't encode /
    # But usually S3 handles standard urllib parse.quote slightly differently, we'll use quote with safe='/-_.~'
    canonical_uri = urllib.parse.quote(uri, safe='/-_.~')
    
    # Split query parameters, sort them, and rebuild.
    canonical_query_string = ""
    if query:
        # S3 requires encoding names and values
        query_params = []
        for qp in query.split('&'):
            if '=' in qp:
                k, v = qp.split('=', 1)
                query_params.append((urllib.parse.quote(k, safe='-_.~'), urllib.parse.quote(v, safe='-_.~')))
            else:
                query_params.append((urllib.parse.quote(qp, safe='-_.~'), ""))
        
        query_params.sort(key=lambda x: x[0] + "=" + x[1])
        canonical_query_string = "&".join([f"{k}={v}" if v else f"{k}=" for k, v in query_params])

    # 2. Canonical Request
    canonical_request = "\n".join([
        method.upper(),
        canonical_uri,
        canonical_query_string,
        canonical_headers,
        signed_headers,
        payload_hash
    ])
    
    # 3. String to sign
    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        algorithm,
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
    ])
    
    # 4. Calculate Signature
    signing_key = get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    
    # 5. Build Authorization header
    authorization_header = (
        f"{algorithm} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    
    final_headers['Authorization'] = authorization_header
    
    return final_headers
