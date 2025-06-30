let walletLoaded = false;
let pendingTransaction = null;

async function fetchWallet() {
    const message = document.getElementById('errorMessage');
    try {
        document.getElementById('balance').textContent = 'Loading...';
        document.getElementById('nonce').textContent = 'Loading...';
        document.getElementById('pending_txs').textContent = 'Loading...';
        document.getElementById('loadingIndicator').classList.remove('hidden');
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
        message.classList.remove('hidden');
        document.getElementById('balance').textContent = 'N/A';
        document.getElementById('nonce').textContent = 'N/A';
        document.getElementById('pending_txs').textContent = '0';
    } finally {
        document.getElementById('loadingIndicator').classList.add('hidden');
    }
}

function showWelcomeView() {
    document.getElementById('welcome-view').classList.remove('hidden');
    document.getElementById('wallet-view').classList.add('hidden');
    document.getElementById('errorMessage').textContent = '';
    document.getElementById('copySuccessMessage').classList.add('hidden');
    walletLoaded = false;
}

function showWalletView() {
    document.getElementById('welcome-view').classList.add('hidden');
    document.getElementById('wallet-view').classList.remove('hidden');
    document.getElementById('errorMessage').textContent = '';
    document.getElementById('copySuccessMessage').classList.add('hidden');
    walletLoaded = true;
    fetchWallet();
}

async function loadWallet(event) {
    event.preventDefault();
    const private_key = document.getElementById('private_key').value.trim();
    const message = document.getElementById('errorMessage');
    const loadButton = document.getElementById('loadButton');
    try {
        if (!private_key) {
            message.textContent = 'Please enter a base64 private key.';
            message.classList.remove('hidden');
            return;
        }
        loadButton.disabled = true;
        loadButton.textContent = 'Loading...';
        document.getElementById('loadingIndicator').classList.remove('hidden');
        const response = await fetch('/api/load_wallet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ private_key })
        });
        const data = await response.json();
        if (response.ok) {
            document.getElementById('copySuccessMessage').textContent = `Wallet loaded! Address: ${data.address}`;
            document.getElementById('copySuccessMessage').classList.remove('hidden');
            showWalletView();
        } else {
            message.textContent = `Error: ${data.detail}`;
            message.classList.remove('hidden');
        }
    } catch (error) {
        message.textContent = `Error: ${error.message}`;
        message.classList.remove('hidden');
    } finally {
        loadButton.disabled = false;
        loadButton.textContent = 'Load Wallet';
        document.getElementById('loadingIndicator').classList.add('hidden');
        document.getElementById('private_key').value = '';
    }
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
    const message = document.getElementById('errorMessage');
    const sendButton = document.getElementById('send-button');
    const confirmButton = document.getElementById('confirm-button');
    try {
        sendButton.disabled = true;
        confirmButton.disabled = true;
        sendButton.textContent = 'Sending...';
        document.getElementById('loadingIndicator').classList.remove('hidden');
        const response = await fetch('/api/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(pendingTransaction)
        });
        const data = await response.json();
        if (response.ok) {
            document.getElementById('copySuccessMessage').textContent = `Transaction successful! Hash: ${data.tx_hash}, Time: ${data.time}`;
            document.getElementById('copySuccessMessage').classList.remove('hidden');
            document.getElementById('to_address').value = '';
            document.getElementById('amount').value = '';
            fetchWallet();
        } else {
            message.textContent = `Error: ${data.detail}`;
            message.classList.remove('hidden');
        }
    } catch (error) {
        message.textContent = `Error: ${error.message}`;
        message.classList.remove('hidden');
    } finally {
        sendButton.disabled = false;
        confirmButton.disabled = false;
        sendButton.textContent = 'Send Transaction';
        document.getElementById('confirmation-modal').classList.add('hidden');
        document.getElementById('loadingIndicator').classList.add('hidden');
        pendingTransaction = null;
    }
}

function cancelTransaction() {
    document.getElementById('confirmation-modal').classList.add('hidden');
    document.getElementById('errorMessage').textContent = '';
    pendingTransaction = null;
}

function copyToClipboard(elementId) {
    const message = document.getElementById('copySuccessMessage');
    const text = elementId === 'address' ? document.getElementById('address').textContent : document.getElementById('private_key').value.trim();
    if (!text) {
        document.getElementById('errorMessage').textContent = 'No text to copy.';
        document.getElementById('errorMessage').classList.remove('hidden');
        return;
    }
    navigator.clipboard.writeText(text).then(() => {
        document.getElementById('copySuccessMessage').textContent = `${elementId === 'address' ? 'Address' : 'Private key'} copied successfully!`;
        document.getElementById('copySuccessMessage').classList.remove('hidden');
        setTimeout(() => {
            document.getElementById('copySuccessMessage').classList.add('hidden');
        }, 3000);
    }).catch(err => {
        document.getElementById('errorMessage').textContent = `Error copying: ${err}`;
        document.getElementById('errorMessage').classList.remove('hidden');
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
