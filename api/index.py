import json
import base64
import hashlib
import time
import re
import random
import aiohttp
import asyncio
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import nacl.signing
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configuration
μ = 1_000_000
# Relaxed regex to allow more flexibility until exact Octra format is confirmed
b58 = re.compile(r"^oct[1-9A-HJ-NP-Za-km-z]{40,48}$")
priv, addr, rpc = None, None, None
sk, pub = None, None
cb, cn, lu, lh = None, None, 0, 0
h = []
session = None
executor = ThreadPoolExecutor(max_workers=1)

class TransactionRequest(BaseModel):
    to: str
    amount: float

class MultiSendRequest(BaseModel):
    recipients: list[dict]

class LoadWalletRequest(BaseModel):
    private_key: str

def base58_encode(data):
    """Encode bytes to base58 (excluding 0, O, I, l)."""
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    x = int.from_bytes(data, 'big')
    result = ''
    while x > 0:
        x, r = divmod(x, 58)
        result = alphabet[r] + result
    # Ensure minimum length
    result = result.rjust(44, alphabet[0])
    return result

def generate_wallet():
    """Generate a new wallet using nacl.signing."""
    try:
        signing_key = nacl.signing.SigningKey.generate()
        private_key = base64.b64encode(signing_key.encode()).decode()
        verify_key = signing_key.verify_key
        public_key = base64.b64encode(verify_key.encode()).decode()
        # Derive address: 'oct' + base58-encoded hash of public key
        pubkey_hash = hashlib.sha256(verify_key.encode()).digest()
        address = "oct" + base58_encode(pubkey_hash)[:45]
        if not b58.match(address):
            # Log for debugging but allow the wallet to be created
            print(f"Generated address {address} does not match expected format")
        return {
            "private_key": private_key,
            "public_key": public_key,
            "address": address,
            "rpc": "https://octra.network"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Wallet generation failed: {str(e)}")

def load_wallet(data=None, base64_key=None):
    """Load wallet from environment variables, file, or base64 private key."""
    global priv, addr, rpc, sk, pub
    try:
        if base64_key:
            # Validate base64 private key
            try:
                decoded_key = base64.b64decode(base64_key, validate=True)
                if len(decoded_key) != 32:  # NaCl signing key is 32 bytes
                    raise ValueError(f"Invalid private key length: {len(decoded_key)} bytes")
            except Exception as e:
                raise ValueError(f"Invalid base64 private key: {str(e)}")
            priv = base64_key
            sk = nacl.signing.SigningKey(decoded_key)
            pub = base64.b64encode(sk.verify_key.encode()).decode()
            pubkey_hash = hashlib.sha256(sk.verify_key.encode()).digest()
            addr = "oct" + base58_encode(pubkey_hash)[:45]
            rpc = "https://octra.network"
            if not b58.match(addr):
                print(f"Loaded address {addr} does not match expected format")
        elif data:
            priv = data.get('priv')
            addr = data.get('addr')
            rpc = data.get('rpc', 'https://octra.network')
            sk = nacl.signing.SigningKey(base64.b64decode(priv))
            pub = base64.b64encode(sk.verify_key.encode()).decode()
        else:
            wallet_path = os.getenv("WALLET_PATH", "/tmp/wallet.json")
            if os.path.exists(wallet_path):
                with open(wallet_path, 'r') as f:
                    data = json.load(f)
                priv = data.get('priv')
                addr = data.get('addr')
                rpc = data.get('rpc', 'https://octra.network')
            else:
                priv = os.getenv("WALLET_PRIVATE_KEY")
                addr = os.getenv("WALLET_ADDRESS")
                rpc = os.getenv("RPC_URL", "https://octra.network")
            if not priv or not addr:
                raise ValueError("Wallet not configured")
            sk = nacl.signing.SigningKey(base64.b64decode(priv))
            pub = base64.b64encode(sk.verify_key.encode()).decode()
        return True
    except Exception as e:
        print(f"Wallet load error: {str(e)}")
        return False

async def req(m, p, d=None, t=10):
    global session
    if not session:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=t))
    try:
        url = f"{rpc}{p}"
        async with getattr(session, m.lower())(url, json=d if m == 'POST' else None) as resp:
            text = await resp.text()
            try:
                j = json.loads(text) if text else None
            except:
                j = None
            return resp.status, text, j
    except asyncio.TimeoutError:
        return 0, "timeout", None
    except Exception as e:
        return 0, str(e), None

async def st():
    global cb, cn, lu
    now = time.time()
    if cb is not None and (now - lu) < 30:
        return cn, cb
    results = await asyncio.gather(
        req('GET', f'/balance/{addr}'),
        req('GET', '/staging', 5),
        return_exceptions=True
    )
    s, t, j = results[0] if not isinstance(results[0], Exception) else (0, str(results[0]), None)
    s2, _, j2 = results[1] if not isinstance(results[1], Exception) else (0, None, None)
    if s == 200 and j:
        cn = int(j.get('nonce', 0))
        cb = float(j.get('balance', 0))
        lu = now
        if s2 == 200 and j2:
            our = [tx for tx in j2.get('staged_transactions', []) if tx.get('from') == addr]
            if our:
                cn = max(cn, max(int(tx.get('nonce', 0)) for tx in our))
    elif s == 404:
        cn, cb, lu = 0, 0.0, now
    elif s == 200 and t and not j:
        try:
            parts = t.strip().split()
            if len(parts) >= 2:
                cb = float(parts[0]) if parts[0].replace('.', '').isdigit() else 0.0
                cn = int(parts[1]) if parts[1].isdigit() else 0
                lu = now
            else:
                cn, cb = None, None
        except:
            cn, cb = None, None
    return cn, cb

async def gh():
    global h, lh
    now = time.time()
    if now - lh < 60 and h:
        return
    s, t, j = await req('GET', f'/address/{addr}?limit=20')
    if s != 200 or (not j and not t):
        return
    if j and 'recent_transactions' in j:
        tx_hashes = [ref["hash"] for ref in j.get('recent_transactions', [])]
        tx_results = await asyncio.gather(*[req('GET', f'/tx/{hash}', 5) for hash in tx_hashes], return_exceptions=True)
        existing_hashes = {tx['hash'] for tx in h}
        nh = []
        for i, (ref, result) in enumerate(zip(j.get('recent_transactions', []), tx_results)):
            if isinstance(result, Exception):
                continue
            s2, _, j2 = result
            if s2 == 200 and j2 and 'parsed_tx' in j2:
                p = j2['parsed_tx']
                tx_hash = ref['hash']
                if tx_hash in existing_hashes:
                    continue
                ii = p.get('to') == addr
                ar = p.get('amount_raw', p.get('amount', '0'))
                a = float(ar) if '.' in str(ar) else int(ar) / μ
                nh.append({
                    'time': datetime.fromtimestamp(p.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                    'hash': tx_hash,
                    'amt': a,
                    'to': p.get('to') if not ii else p.get('from'),
                    'type': 'in' if ii else 'out',
                    'ok': True,
                    'nonce': p.get('nonce', 0),
                    'epoch': ref.get('epoch', 0)
                })
        oh = datetime.now() - timedelta(hours=1)
        h[:] = sorted(nh + [tx for tx in h if datetime.strptime(tx.get('time', datetime.now().strftime('%Y-%m-%d %H:%M:%S')), '%Y-%m-%d %H:%M:%S') > oh], key=lambda x: datetime.strptime(x['time'], '%Y-%m-%d %H:%M:%S'), reverse=True)[:50]
        lh = now
    elif s == 404 or (s == 200 and t and 'no transactions' in t.lower()):
        h.clear()
        lh = now

def mk(to, a, n):
    tx = {
        "from": addr,
        "to_": to,
        "amount": str(int(a * μ)),
        "nonce": int(n),
        "ou": "1" if a < 1000 else "3",
        "timestamp": time.time() + random.random() * 0.01
    }
    bl = json.dumps(tx, separators=(",", ":"))
    sig = base64.b64encode(sk.sign(bl.encode()).signature).decode()
    tx.update(signature=sig, public_key=pub)
    return tx, hashlib.sha256(bl.encode()).hexdigest()

async def snd(tx):
    t0 = time.time()
    s, t, j = await req('POST', '/send-tx', tx)
    dt = time.time() - t0
    if s == 200:
        if j and j.get('status') == 'accepted':
            return True, j.get('tx_hash', ''), dt, j
        elif t.lower().startswith('ok'):
            return True, t.split()[-1], dt, None
    return False, json.dumps(j) if j else t, dt, j

@app.on_event("startup")
async def startup_event():
    try:
        if not load_wallet():
            # Generate a new wallet if none is configured
            wallet = generate_wallet()
            global priv, addr, rpc, sk, pub
            priv = wallet['private_key']
            addr = wallet['address']
            rpc = wallet['rpc']
            sk = nacl.signing.SigningKey(base64.b64decode(priv))
            pub = base64.b64encode(sk.verify_key.encode()).decode()
            # Save to /tmp/wallet.json
            try:
                with open('/tmp/wallet.json', 'w') as f:
                    json.dump(wallet, f, indent=2)
            except Exception as e:
                print(f"Failed to save wallet: {str(e)}")
    except Exception as e:
        print(f"Startup error: {str(e)}")

@app.on_event("shutdown")
async def shutdown_event():
    global session
    if session:
        await session.close()
    executor.shutdown(wait=False)

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    try:
        with open("static/index.html") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to serve index: {str(e)}")

@app.get("/api/wallet")
async def get_wallet():
    try:
        if not addr:
            raise HTTPException(status_code=400, detail="No wallet loaded")
        n, b = await st()
        await gh()
        s, _, j = await req('GET', '/staging', 2)
        sc = len([tx for tx in j.get('staged_transactions', []) if tx.get('from') == addr]) if j else 0
        return {
            "address": addr,
            "balance": f"{b:.6f} oct" if b is not None else "N/A",
            "nonce": n if n is not None else "N/A",
            "public_key": pub,
            "pending_txs": sc,
            "transactions": sorted(h, key=lambda x: datetime.strptime(x['time'], '%Y-%m-%d %H:%M:%S'), reverse=True)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get wallet: {str(e)}")

@app.post("/api/send")
async def send_transaction(tx: TransactionRequest):
    try:
        if not b58.match(tx.to):
            raise HTTPException(status_code=400, detail="Invalid address")
        if not re.match(r"^\d+(\.\d+)?$", str(tx.amount)) or tx.amount <= 0:
            raise HTTPException(status_code=400, detail="Invalid amount")
        n, b = await st()
        if n is None:
            raise HTTPException(status_code=500, detail="Failed to get nonce")
        if not b or b < tx.amount:
            raise HTTPException(status_code=400, detail=f"Insufficient balance ({b:.6f} < {tx.amount})")
        t, _ = mk(tx.to, tx.amount, n + 1)
        ok, hs, dt, r = await snd(t)
        if ok:
            h.append({
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'hash': hs,
                'amt': tx.amount,
                'to': tx.to,
                'type': 'out',
                'ok': True
            })
            global lu
            lu = 0
            return {
                "status": "success",
                "tx_hash": hs,
                "time": f"{dt:.2f}s",
                "pool_size": r.get('pool_info', {}).get('total_pool_size', 0) if r else 0
            }
        raise HTTPException(status_code=400, detail=f"Transaction failed: {hs}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Send transaction failed: {str(e)}")

@app.post("/api/multi_send")
async def multi_send(data: MultiSendRequest):
    try:
        recipients = [(r["to"], r["amount"]) for r in data.recipients]
        tot = sum(a for _, a in recipients)
        for to, a in recipients:
            if not b58.match(to):
                raise HTTPException(status_code=400, detail=f"Invalid address: {to}")
            if not re.match(r"^\d+(\.\d+)?$", str(a)) or a <= 0:
                raise HTTPException(status_code=400, detail=f"Invalid amount: {a}")
        n, b = await st()
        if n is None:
            raise HTTPException(status_code=500, detail="Failed to get nonce")
        if not b or b < tot:
            raise HTTPException(status_code=400, detail=f"Insufficient balance ({b:.6f} < {tot})")
        batch_size = 5
        batches = [recipients[i:i+batch_size] for i in range(0, len(recipients), batch_size)]
        s_total, f_total = 0, 0
        results = []
        for batch_idx, batch in enumerate(batches):
            tasks = []
            for i, (to, a) in enumerate(batch):
                idx = batch_idx * batch_size + i
                t, _ = mk(to, a, n + 1 + idx)
                tasks.append(snd(t))
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, (result, (to, a)) in enumerate(zip(batch_results, batch)):
                if isinstance(result, Exception):
                    f_total += 1
                    results.append({"to": to, "amount": a, "status": "failed", "error": str(result)})
                else:
                    ok, hs, _, _ = result
                    if ok:
                        s_total += 1
                        h.append({
                            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'hash': hs,
                            'amt': a,
                            'to': to,
                            'type': 'out',
                            'ok': True
                        })
                        results.append({"to": to, "amount": a, "status": "success", "tx_hash": hs})
                    else:
                        f_total += 1
                        results.append({"to": to, "amount": a, "status": "failed", "error": hs})
        global lu
        lu = 0
        return {"success": s_total, "failed": f_total, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Multi-send failed: {str(e)}")

@app.get("/api/export")
async def export_keys():
    try:
        if not priv or not addr or not pub:
            raise HTTPException(status_code=400, detail="No wallet loaded")
        return {
            "address": addr,
            "private_key": priv,
            "public_key": pub
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export keys failed: {str(e)}")

@app.post("/api/clear_history")
async def clear_history():
    try:
        global h, lh
        h.clear()
        lh = 0
        return {"status": "history cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clear history failed: {str(e)}")

@app.post("/api/generate_wallet")
async def api_generate_wallet():
    try:
        wallet = generate_wallet()
        # Save to /tmp/wallet.json (ephemeral)
        try:
            with open('/tmp/wallet.json', 'w') as f:
                json.dump(wallet, f, indent=2)
        except Exception as e:
            print(f"Failed to save wallet: {str(e)}")
        # Update global variables
        global priv, addr, rpc, sk, pub
        priv = wallet['private_key']
        addr = wallet['address']
        rpc = wallet['rpc']
        sk = nacl.signing.SigningKey(base64.b64decode(priv))
        pub = base64.b64encode(sk.verify_key.encode()).decode()
        return wallet
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Wallet generation failed: {str(e)}")

@app.post("/api/load_wallet")
async def load_base64_wallet(data: LoadWalletRequest):
    try:
        if not load_wallet(base64_key=data.private_key):
            raise HTTPException(status_code=400, detail="Invalid base64 private key")
        # Save to /tmp/wallet.json
        try:
            with open('/tmp/wallet.json', 'w') as f:
                json.dump({"priv": priv, "addr": addr, "rpc": rpc}, f, indent=2)
        except Exception as e:
            print(f"Failed to save wallet: {str(e)}")
        return {"status": "wallet loaded", "address": addr}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Load wallet failed: {str(e)}")
