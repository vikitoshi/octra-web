import json
import base64
import hashlib
import time
import re
import random
import aiohttp
import asyncio
import os
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import nacl.signing
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel
from typing import Dict
import logging

# Configure logging for Vercel
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add session middleware with a fixed secret key
app.add_middleware(SessionMiddleware, secret_key="fixed-secret-key-1234567890", session_cookie="session_id", max_age=None)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configuration
μ = 1_000_000
b58 = re.compile(r"^oct[1-9A-HJ-NP-Za-km-z]{40,48}$")
sessions: Dict[str, Dict] = {}
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
    try:
        alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
        x = int.from_bytes(data, 'big')
        result = ''
        while x > 0:
            x, r = divmod(x, 58)
            result = alphabet[r] + result
        result = result.rjust(44, alphabet[0])
        return result
    except Exception as e:
        logger.error(f"Base58 encoding error: {str(e)}")
        raise ValueError(f"Base58 encoding failed: {str(e)}")

def generate_wallet():
    """Generate a new wallet using nacl.signing."""
    try:
        signing_key = nacl.signing.SigningKey.generate()
        private_key = base64.b64encode(signing_key.encode()).decode()
        verify_key = signing_key.verify_key
        public_key = base64.b64encode(verify_key.encode()).decode()
        pubkey_hash = hashlib.sha256(verify_key.encode()).digest()
        address = "oct" + base58_encode(pubkey_hash)[:45]
        if not b58.match(address):
            logger.warning(f"Generated address {address} does not match expected format")
        return {
            "private_key": private_key,
            "public_key": public_key,
            "address": address,
            "rpc": "https://octra.network"
        }
    except Exception as e:
        logger.error(f"Wallet generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Wallet generation failed: {str(e)}")

def load_wallet(request: Request, base64_key: str):
    """Load wallet from base64 private key into session."""
    try:
        decoded_key = base64.b64decode(base64_key, validate=True)
        if len(decoded_key) != 32:
            raise ValueError(f"Invalid private key length: {len(decoded_key)} bytes")
        sk = nacl.signing.SigningKey(decoded_key)
        pub = base64.b64encode(sk.verify_key.encode()).decode()
        pubkey_hash = hashlib.sha256(sk.verify_key.encode()).digest()
        addr = "oct" + base58_encode(pubkey_hash)[:45]
        if not b58.match(addr):
            logger.warning(f"Loaded address {addr} does not match expected format")
        session_id = request.session.get("session_id")
        if not session_id:
            session_id = os.urandom(16).hex()
            request.session["session_id"] = session_id
        sessions[session_id] = {
            "priv": base64_key,
            "addr": addr,
            "rpc": "https://octra.network",
            "sk": sk,
            "pub": pub,
            "cb": None,
            "cn": None,
            "lu": 0,
            "lh": 0,
            "h": []
        }
        return True
    except Exception as e:
        logger.error(f"Wallet load error: {str(e)}")
        return False

async def get_session(request: Request):
    """Get session data for the current user."""
    try:
        session_id = request.session.get("session_id")
        if not session_id or session_id not in sessions:
            raise HTTPException(status_code=400, detail="No wallet loaded. Generate or load a wallet first.")
        return sessions[session_id]
    except Exception as e:
        logger.error(f"Session retrieval error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Session error: {str(e)}")

async def req(rpc: str, m: str, p: str, d=None, t=10):
    """Make HTTP request with a new aiohttp.ClientSession per call."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=t)) as session:
            url = f"{rpc}{p}"
            async with getattr(session, m.lower())(url, json=d if m == 'POST' else None) as resp:
                text = await resp.text()
                try:
                    j = json.loads(text) if text else None
                except:
                    j = None
                return resp.status, text, j
    except asyncio.TimeoutError:
        logger.error("Request timeout")
        return 0, "timeout", None
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        return 0, str(e), None

async def st(session_data: Dict):
    """Get balance and nonce for the session's wallet."""
    try:
        now = time.time()
        if session_data["cb"] is not None and (now - session_data["lu"]) < 30:
            return session_data["cn"], session_data["cb"]
        results = await asyncio.gather(
            req(session_data["rpc"], 'GET', f'/balance/{session_data["addr"]}'),
            req(session_data["rpc"], 'GET', '/staging', 5),
            return_exceptions=True
        )
        s, t, j = results[0] if not isinstance(results[0], Exception) else (0, str(results[0]), None)
        s2, _, j2 = results[1] if not isinstance(results[1], Exception) else (0, None, None)
        if s == 200 and j:
            session_data["cn"] = int(j.get('nonce', 0))
            session_data["cb"] = float(j.get('balance', 0))
            session_data["lu"] = now
            if s2 == 200 and j2:
                our = [tx for tx in j2.get('staged_transactions', []) if tx.get('from') == session_data["addr"]]
                if our:
                    session_data["cn"] = max(session_data["cn"], max(int(tx.get('nonce', 0)) for tx in our))
        elif s == 404:
            session_data["cn"], session_data["cb"], session_data["lu"] = 0, 0.0, now
        elif s == 200 and t and not j:
            try:
                parts = t.strip().split()
                if len(parts) >= 2:
                    session_data["cb"] = float(parts[0]) if parts[0].replace('.', '').isdigit() else 0.0
                    session_data["cn"] = int(parts[1]) if parts[1].isdigit() else 0
                    session_data["lu"] = now
                else:
                    session_data["cn"], session_data["cb"] = None, None
            except:
                session_data["cn"], session_data["cb"] = None, None
        return session_data["cn"], session_data["cb"]
    except Exception as e:
        logger.error(f"Status fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch status: {str(e)}")

async def gh(session_data: Dict):
    """Get transaction history for the session's wallet."""
    try:
        now = time.time()
        if now - session_data["lh"] < 60 and session_data["h"]:
            return
        s, t, j = await req(session_data["rpc"], 'GET', f'/address/{session_data["addr"]}?limit=20')
        if s != 200 or (not j and not t):
            return
        if j and 'recent_transactions' in j:
            tx_hashes = [ref["hash"] for ref in j.get('recent_transactions', [])]
            tx_results = await asyncio.gather(*[req(session_data["rpc"], 'GET', f'/tx/{hash}', 5) for hash in tx_hashes], return_exceptions=True)
            existing_hashes = {tx['hash'] for tx in session_data["h"]}
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
                    ii = p.get('to') == session_data["addr"]
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
            session_data["h"] = sorted(nh + [tx for tx in session_data["h"] if datetime.strptime(tx.get('time', datetime.now().strftime('%Y-%m-%d %H:%M:%S')), '%Y-%m-%d %H:%M:%S') > oh], key=lambda x: datetime.strptime(x['time'], '%Y-%m-%d %H:%M:%S'), reverse=True)[:50]
            session_data["lh"] = now
        elif s == 404 or (s == 200 and t and 'no transactions' in t.lower()):
            session_data["h"].clear()
            session_data["lh"] = now
    except Exception as e:
        logger.error(f"History fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")

def mk(session_data: Dict, to: str, a: float, n: int):
    """Create a signed transaction."""
    try:
        tx = {
            "from": session_data["addr"],
            "to_": to,
            "amount": str(int(a * μ)),
            "nonce": int(n),
            "ou": "1" if a < 1000 else "3",
            "timestamp": time.time() + random.random() * 0.01
        }
        bl = json.dumps(tx, separators=(",", ":"))
        sig = base64.b64encode(session_data["sk"].sign(bl.encode()).signature).decode()
        tx.update(signature=sig, public_key=session_data["pub"])
        return tx, hashlib.sha256(bl.encode()).hexdigest()
    except Exception as e:
        logger.error(f"Transaction creation error: {str(e)}")
        raise ValueError(f"Transaction creation failed: {str(e)}")

async def snd(session_data: Dict, tx):
    """Send a transaction."""
    try:
        t0 = time.time()
        s, t, j = await req(session_data["rpc"], 'POST', '/send-tx', tx)
        dt = time.time() - t0
        if s == 200:
            if j and j.get('status') == 'accepted':
                return True, j.get('tx_hash', ''), dt, j
            elif t.lower().startswith('ok'):
                return True, t.split()[-1], dt, None
        return False, json.dumps(j) if j else t, dt, j
    except Exception as e:
        logger.error(f"Send transaction error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Send transaction failed: {str(e)}")

@app.on_event("startup")
async def startup_event():
    logger.info("Application startup")
    # No wallet loading on startup
    pass

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown")
    executor.shutdown(wait=False)

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    try:
        with open("static/index.html") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        logger.error(f"Index serving error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to serve index: {str(e)}")

@app.get("/api/wallet")
async def get_wallet(session_data: Dict = Depends(get_session)):
    try:
        n, b = await st(session_data)
        await gh(session_data)
        s, _, j = await req(session_data["rpc"], 'GET', '/staging', 2)
        sc = len([tx for tx in j.get('staged_transactions', []) if tx.get('from') == session_data["addr"]]) if j else 0
        return {
            "address": session_data["addr"],
            "balance": f"{b:.6f} oct" if b is not None else "N/A",
            "nonce": n if n is not None else "N/A",
            "public_key": session_data["pub"],
            "pending_txs": sc,
            "transactions": sorted(session_data["h"], key=lambda x: datetime.strptime(x['time'], '%Y-%m-%d %H:%M:%S'), reverse=True)
        }
    except Exception as e:
        logger.error(f"Get wallet error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get wallet: {str(e)}")

@app.post("/api/send")
async def send_transaction(tx: TransactionRequest, session_data: Dict = Depends(get_session)):
    try:
        if not b58.match(tx.to):
            raise HTTPException(status_code=400, detail="Invalid address")
        if not re.match(r"^\d+(\.\d+)?$", str(tx.amount)) or tx.amount <= 0:
            raise HTTPException(status_code=400, detail="Invalid amount")
        n, b = await st(session_data)
        if n is None:
            raise HTTPException(status_code=500, detail="Failed to get nonce")
        if not b or b < tx.amount:
            raise HTTPException(status_code=400, detail=f"Insufficient balance ({b:.6f} < {tx.amount})")
        t, _ = mk(session_data, tx.to, tx.amount, n + 1)
        ok, hs, dt, r = await snd(session_data, t)
        if ok:
            session_data["h"].append({
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'hash': hs,
                'amt': tx.amount,
                'to': tx.to,
                'type': 'out',
                'ok': True
            })
            session_data["lu"] = 0
            return {
                "status": "success",
                "tx_hash": hs,
                "time": f"{dt:.2f}s",
                "pool_size": r.get('pool_info', {}).get('total_pool_size', 0) if r else 0
            }
        raise HTTPException(status_code=400, detail=f"Transaction failed: {hs}")
    except Exception as e:
        logger.error(f"Send transaction error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Send transaction failed: {str(e)}")

@app.post("/api/multi_send")
async def multi_send(data: MultiSendRequest, session_data: Dict = Depends(get_session)):
    try:
        recipients = [(r["to"], r["amount"]) for r in data.recipients]
        tot = sum(a for _, a in recipients)
        for to, a in recipients:
            if not b58.match(to):
                raise HTTPException(status_code=400, detail=f"Invalid address: {to}")
            if not re.match(r"^\d+(\.\d+)?$", str(a)) or a <= 0:
                raise HTTPException(status_code=400, detail=f"Invalid amount: {a}")
        n, b = await st(session_data)
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
                t, _ = mk(session_data, to, a, n + 1 + idx)
                tasks.append(snd(session_data, t))
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, (result, (to, a)) in enumerate(zip(batch_results, batch)):
                if isinstance(result, Exception):
                    f_total += 1
                    results.append({"to": to, "amount": a, "status": "failed", "error": str(result)})
                else:
                    ok, hs, _, _ = result
                    if ok:
                        s_total += 1
                        session_data["h"].append({
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
        session_data["lu"] = 0
        return {"success": s_total, "failed": f_total, "results": results}
    except Exception as e:
        logger.error(f"Multi-send error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Multi-send failed: {str(e)}")

@app.get("/api/export")
async def export_keys(session_data: Dict = Depends(get_session)):
    try:
        return {
            "address": session_data["addr"],
            "private_key": session_data["priv"],
            "public_key": session_data["pub"]
        }
    except Exception as e:
        logger.error(f"Export keys error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Export keys failed: {str(e)}")

@app.post("/api/clear_history")
async def clear_history(session_data: Dict = Depends(get_session)):
    try:
        session_data["h"].clear()
        session_data["lh"] = 0
        return {"status": "history cleared"}
    except Exception as e:
        logger.error(f"Clear history error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Clear history failed: {str(e)}")

@app.post("/api/generate_wallet")
async def api_generate_wallet(request: Request):
    try:
        wallet = generate_wallet()
        session_id = request.session.get("session_id")
        if not session_id:
            session_id = os.urandom(16).hex()
            request.session["session_id"] = session_id
        sessions[session_id] = {
            "priv": wallet["private_key"],
            "addr": wallet["address"],
            "rpc": wallet["rpc"],
            "sk": nacl.signing.SigningKey(base64.b64decode(wallet["private_key"])),
            "pub": wallet["public_key"],
            "cb": None,
            "cn": None,
            "lu": 0,
            "lh": 0,
            "h": []
        }
        return wallet
    except Exception as e:
        logger.error(f"Generate wallet error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Wallet generation failed: {str(e)}")

@app.post("/api/load_wallet")
async def load_base64_wallet(data: LoadWalletRequest, request: Request):
    try:
        if not load_wallet(request, data.private_key):
            raise HTTPException(status_code=400, detail="Invalid base64 private key")
        return {"status": "wallet loaded", "address": sessions[request.session["session_id"]]["addr"]}
    except Exception as e:
        logger.error(f"Load wallet error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Load wallet failed: {str(e)}")
