let walletLoaded = false;

async function fetchWallet() {
    const message = document.getElementById('message');
    try {
        const response = await fetch('/api/wallet');
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to fetch wallet');
        }
        const data = await response.json();
        document.getElementById('address').textContent = data.address || 'N/A';
        document.getElementById('balance').textContent = data.balance;
        document.getElementById('nonce').textContent = data.nonce;
        document.getElementById('pending_txs').textContent = data.pending_txs;
    } catch (error) {
        message.textContent = `Error: ${error.message}`;
        message.className = 'error';
    }
}

function showWelcomeView() {
    document.getElementById('welcome-view').classList.remove('hidden');
    document.getElementById('wallet-view').classList.add('hidden');
    document.getElementById('generate-wallet-form').classList.add('hidden');
    document.getElementById('load-wallet-form').classList.add('hidden');
    document.getElementById('message').textContent = '';
    walletLoaded = false;
}

function showWalletView() {
    document.getElementById('welcome-view').classList.add('hidden');
    document.getElementById('wallet-view').classList.remove('hidden');
    document.getElementById('generate-wallet-form').classList.add('hidden');
    document.getElementById('load-wallet-form').classList.add('hidden');
    walletLoaded = true;
    fetchWallet();
}

function showGenerateWalletForm() {
    document.getElementById('welcome-view').classList.add('hidden');
    document.getElementById('wallet-view').classList.add('hidden');
    document.getElementById('generate-wallet-form').classList.remove('hidden');
    document.getElementById('load-wallet-form').classList.add('hidden');
    document.getElementById('message').textContent = '';
}

function showLoadWalletForm() {
    document.getElementById('welcome-view').classList.add('hidden');
    document.getElementById('wallet-view').classList.add('hidden');
    document.getElementById('generate-wallet-form').classList.add('hidden');
    document.getElementById('load-wallet-form').classList.remove('hidden');
    document.getElementById('message').textContent = '';
}

async function sendTransaction(event) {
    event.preventDefault();
    const to = document.getElementById('to_address').value;
    const amount = parseFloat(document.getElementById('amount').value);
    const message = document.getElementById('message');
    try {
        const response = await fetch('/api/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ to, amount })
        });
        const data = await response.json();
        if (response.ok) {
            message.textContent = `Transaction successful! Hash: ${data.tx_hash}, Time: ${data.time}`;
            message.className = 'success';
            fetchWallet();
        } else {
            message.textContent = `Error: ${data.detail}`;
            message.className = 'error';
        }
    } catch (error) {
        message.textContent = `Error: ${error.message}`;
        message.className = 'error';
    }
}

async function generateWallet() {
    const message = document.getElementById('message');
    try {
        const response = await fetch('/api/generate_wallet', { method: 'POST' });
        const data = await response.json();
        if (response.ok) {
            message.textContent = `New wallet generated! Address: ${data.address}, Private Key: ${data.private_key} (copy this securely!)`;
            message.className = 'success';
            showWalletView();
        } else {
            message.textContent = `Error: ${data.detail}`;
            message.className = 'error';
        }
    } catch (error) {
        message.textContent = `Error: ${error.message}`;
        message.className = 'error';
    }
}

async function loadWallet(event) {
    event.preventDefault();
    const private_key = document.getElementById('private_key').value;
    const message = document.getElementById('message');
    try {
        const response = await fetch('/api/load_wallet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ private_key })
        });
        const data = await response.json();
        if (response.ok) {
            message.textContent = `Wallet loaded! Address: ${data.address}`;
            message.className = 'success';
            showWalletView();
        } else {
            message.textContent = `Error: ${data.detail}`;
            message.className = 'error';
        }
    } catch (error) {
        message.textContent = `Error: ${error.message}`;
        message.className = 'error';
    }
}

function resetWallet() {
    showWelcomeView();
}

window.onload = () => {
    showWelcomeView();
};
