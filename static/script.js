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
        document.getElementById('public_key').textContent = data.public_key ? data.public_key.substring(0, 20) + '...' : 'N/A';
        document.getElementById('pending_txs').textContent = data.pending_txs;
        const tbody = document.querySelector('#transactions tbody');
        tbody.innerHTML = '';
        data.transactions.forEach(tx => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${tx.time}</td>
                <td>${tx.type}</td>
                <td>${tx.amt.toFixed(6)}</td>
                <td>${tx.to.substring(0, 20)}...</td>
                <td>${tx.epoch ? `Epoch ${tx.epoch}` : 'Pending'}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (error) {
        message.textContent = `Error: ${error.message}. Please generate or load a wallet.`;
        message.className = 'error';
        document.getElementById('address').textContent = 'N/A';
        document.getElementById('balance').textContent = 'N/A';
        document.getElementById('nonce').textContent = 'N/A';
        document.getElementById('public_key').textContent = 'N/A';
        document.getElementById('pending_txs').textContent = '0';
        document.querySelector('#transactions tbody').innerHTML = '';
    }
}

function showSendForm() {
    hideForms();
    document.getElementById('send-form').classList.add('visible');
}

function showMultiSendForm() {
    hideForms();
    document.getElementById('multi-send-form').classList.add('visible');
}

function showGenerateWalletForm() {
    hideForms();
    document.getElementById('generate-wallet-form').classList.add('visible');
}

function showLoadWalletForm() {
    hideForms();
    document.getElementById('load-wallet-form').classList.add('visible');
}

function hideForms() {
    document.querySelectorAll('.form').forEach(form => form.classList.remove('visible'));
    document.getElementById('message').textContent = '';
}

function addRecipient() {
    const recipients = document.getElementById('recipients');
    const div = document.createElement('div');
    div.className = 'recipient';
    div.innerHTML = `
        <label>Address:</label>
        <input type="text" class="recipient-address" required>
        <label>Amount:</label>
        <input type="number" step="0.000001" class="recipient-amount" required>
    `;
    recipients.appendChild(div);
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
            hideForms();
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

async function multiSend(event) {
    event.preventDefault();
    const recipients = Array.from(document.querySelectorAll('.recipient')).map(div => ({
        to: div.querySelector('.recipient-address').value,
        amount: parseFloat(div.querySelector('.recipient-amount').value)
    }));
    const message = document.getElementById('message');
    try {
        const response = await fetch('/api/multi_send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ recipients })
        });
        const data = await response.json();
        if (response.ok) {
            message.textContent = `Completed: ${data.success} success, ${data.failed} failed`;
            message.className = data.failed === 0 ? 'success' : 'error';
            hideForms();
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

async function exportKeys() {
    hideForms();
    const form = document.getElementById('export-keys');
    const message = document.getElementById('message');
    try {
        const response = await fetch('/api/export');
        const data = await response.json();
        if (response.ok) {
            document.getElementById('export_address').textContent = data.address;
            document.getElementById('export_private_key').textContent = data.private_key;
            document.getElementById('export_public_key').textContent = data.public_key;
            form.classList.add('visible');
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
            message.textContent = `New wallet generated! Address: ${data.address}, Private Key: ${data.private_key}, Public Key: ${data.public_key}. Save your private key securely!`;
            message.className = 'success';
            hideForms();
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
            message.textContent = `Wallet loaded! Address: ${data.address}. Save your private key securely!`;
            message.className = 'success';
            hideForms();
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

function copyToClipboard(elementId) {
    const text = document.getElementById(elementId).textContent;
    navigator.clipboard.writeText(text).then(() => {
        document.getElementById('message').textContent = 'Copied to clipboard!';
        document.getElementById('message').className = 'success';
    }).catch(err => {
        document.getElementById('message').textContent = `Error copying: ${err}`;
        document.getElementById('message').className = 'error';
    });
}

function refreshWallet() {
    fetchWallet();
}

window.onload = fetchWallet;
