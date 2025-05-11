# crypto_ops.py
from cryptography.hazmat.primitives import hashes as hsh
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC as PBK
from cryptography.hazmat.primitives.ciphers import Cipher as Cp, algorithms as alg, modes as md
from cryptography.hazmat.backends import default_backend # Recommended to specify backend
import base64 as b64
import os as osy
from config import MASTER_KEY as M1, IV_KEY as I1

# It's good practice to ensure M1 (MASTER_KEY) and I1 (IV_KEY/salt) are bytes.
# If they are strings from config, encode them.
# However, the current code encodes them inside dyk, which is fine.

def dyk(pwd: str = M1, slt: str = I1, l: int = 16): # Type hints for clarity
    pw_bytes = pwd.encode('utf-8') # Specify encoding
    sl_bytes = slt.encode('utf-8') # Specify encoding
    
    kdf = PBK(
        algorithm=hsh.SHA256(),
        length=l,
        salt=sl_bytes, # Use encoded salt
        iterations=100000, # Consider increasing iterations for stronger key derivation
        backend=default_backend() # Specify backend
    )
    return kdf.derive(pw_bytes) # Derive from encoded password

def ecs(s: str) -> str:
    k = dyk() # Key derivation
    n = osy.urandom(12)  # GCM recommended nonce length is 12 bytes
    
    cp = Cp(alg.AES(k), md.GCM(n), backend=default_backend())
    enc = cp.encryptor()
    
    p_bytes = s.encode('utf-8') # Specify encoding for the plaintext
    ct = enc.update(p_bytes) + enc.finalize()
    tg = enc.tag # GCM tag
    
    # Prepend nonce and tag to ciphertext for easy retrieval during decryption
    # Order: nonce (12 bytes) + tag (16 bytes default for AES-GCM) + ciphertext
    encd = b64.b64encode(n + tg + ct).decode('utf-8') # Specify encoding for the output string
    return encd

def dcs(ed: str) -> str:
    k = dyk() # Key derivation
    dat_bytes = b64.b64decode(ed.encode('utf-8')) # Specify encoding for the input string
    
    # Extract nonce, tag, and ciphertext based on their lengths
    n = dat_bytes[:12]      # Nonce (12 bytes)
    tg = dat_bytes[12:28]   # Tag (16 bytes)
    ct = dat_bytes[28:]     # Ciphertext
    
    cp = Cp(alg.AES(k), md.GCM(n, tg), backend=default_backend()) # Provide tag to GCM for verification
    dec = cp.decryptor()
    
    try:
        res_bytes = dec.update(ct) + dec.finalize() # This will raise InvalidTag if auth fails
        return res_bytes.decode('utf-8') # Specify encoding for the result string
    except Exception as e: # Catch potential decryption errors (e.g., InvalidTag)
        # Handle decryption failure appropriately, e.g., log error, return None, or raise custom exception
        # For now, re-raising the exception is one option.
        # print(f"Decryption failed: {e}") # Or log it
        raise # Or return an error indicator: return None
