let walletLoaded = false;
let pendingTransaction = null;

async function fetchWallet() {
    const message = document.getElementById('message');
    try {
        document.getElementById('balance').textContent = 'Loading...';
        document.getElementById('nonce').textContent = 'Loading...';
        document.getElementById('pending_txs').textContent = 'Loading...';
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
        const tbody = document.getElementById('transactions');
        tbody.innerHTML = '';
        data.transactions.slice(0, 5).forEach(tx => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${tx.time}</td>
                <td>${tx.type}</td>
                <td>${tx.amt.toFixed(6)}</td>
                <td class="break-all">${tx.to.substring(0, 10)}...</td>
                <td>${tx.epoch ? `Epoch ${tx.epoch}` : 'Pending'}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (error) {
        message.textContent = `Error: ${error.message}`;
        message.className = 'error';
        document.getElementById('balance').textContent = 'N/A';
        document.getElementById('nonce').textContent = 'N/A';
        document.getElementById('pending_txs').textContent = '0';
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
    pendingTransaction = { to, amount };
    document.getElementById('confirm-amount').textContent = amount;
    document.getElementById('confirm-address').textContent = to.substring(0, 10) + '...';
    document.getElementById('confirmation-modal').classList.remove('hidden');
}

async function confirmTransaction() {
    const message = document.getElementById('message');
    const sendButton = document.getElementById('send-button');
    const confirmButton = document.getElementById('confirm-button');
    try {
        sendButton.disabled = true;
        confirmButton.disabled = true;
        sendButton.textContent = 'Sending...';
        const response = await fetch('/api/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(pendingTransaction)
        });
        const data = await response.json();
        if (response.ok) {
            message.textContent = `Transaction successful! Hash: ${data.tx_hash}, Time: ${data.time}`;
            message.className = 'success';
            document.getElementById('to_address').value = '';
            document.getElementById('amount').value = '';
            fetchWallet();
        } else {
            message.textContent = `Error: ${data.detail}`;
            message.className = 'error';
        }
    } catch (error) {
        message.textContent = `Error: ${error.message}`;
        message.className = 'error';
    } finally {
        sendButton.disabled = false;
        confirmButton.disabled = false;
        sendButton.textContent = 'Send';
        document.getElementById('confirmation-modal').classList.add('hidden');
        pendingTransaction = null;
    }
}

function cancelTransaction() {
    document.getElementById('confirmation-modal').classList.add('hidden');
    pendingTransaction = null;
}

async function generateWallet() {
    const message = document.getElementById('message');
    const generateButton = document.getElementById('generate-button');
    try {
        generateButton.disabled = true;
        generateButton.textContent = 'Generating...';
        const response = await fetch('/api/generate_wallet', { method: 'POST' });
        const data = await response.json();
        if (response.ok) {
            message.innerHTML = `New wallet generated! Address: ${data.address} <button onclick="copyToClipboard('${data.address}')" class="text-blue-500 hover:text-blue-700 text-sm ml-2">Copy</button><br>Private Key: ${data.private_key} <button onclick="copyToClipboard('${data.private_key}')" class="text-blue-500 hover:text-blue-700 text-sm ml-2">Copy</button> (save securely!)`;
            message.className = 'success';
            showWalletView();
        } else {
            message.textContent = `Error: ${data.detail}`;
            message.className = 'error';
        }
    } catch (error) {
        message.textContent = `Error: ${error.message}`;
        message.className = 'error';
    } finally {
        generateButton.disabled = false;
        generateButton.textContent = 'Generate';
    }
}

async function loadWallet(event) {
    event.preventDefault();
    const private_key = document.getElementById('private_key').value;
    const message = document.getElementById('message');
    const loadButton = document.getElementById('load-button');
    try {
        loadButton.disabled = true;
        loadButton.textContent = 'Loading...';
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
    } finally {
        loadButton.disabled = false;
        loadButton.textContent = 'Load';
        document.getElementById('private_key').value = '';
    }
}

function copyToClipboard(text) {
    const message = document.getElementById('message');
    navigator.clipboard.writeText(text).then(() => {
        message.textContent = 'Copied to clipboard!';
        message.className = 'success';
    }).catch(err => {
        message.textContent = `Error copying: ${err}`;
        message.className = 'error';
    });
}

function refreshBalance() {
    fetchWallet();
}

function resetWallet() {
    showWelcomeView();
}

window.onload = () => {
    showWelcomeView();
};