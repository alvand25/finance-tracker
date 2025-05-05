// Receipt upload handling

const uploadStatus = document.getElementById('upload-status');
const processingOverlay = document.getElementById('processing-overlay');
const receiptModal = document.getElementById('receipt-modal');
const itemList = document.getElementById('item-list');
const receiptPreview = document.getElementById('receipt-preview');
const confidenceDisplay = document.getElementById('confidence-display');
const totalDisplay = document.getElementById('total-display');
const debugInfo = document.getElementById('debug-info');

// Initialize UI state
let isUploading = false;
let currentProgress = 0;

function showError(message, details = null) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4';
    errorDiv.innerHTML = `
        <strong class="font-bold">Error: </strong>
        <span class="block sm:inline">${message}</span>
        ${details ? `
            <details class="mt-2 text-sm">
                <summary class="cursor-pointer">Show Details</summary>
                <pre class="mt-2 p-2 bg-red-50 rounded overflow-auto">${JSON.stringify(details, null, 2)}</pre>
            </details>
        ` : ''}
        <button class="absolute top-0 right-0 px-4 py-3" onclick="this.parentElement.remove()">
            <span class="sr-only">Dismiss</span>
            <svg class="h-4 w-4 fill-current" role="button" viewBox="0 0 20 20">
                <path d="M14.348 14.849a1.2 1.2 0 0 1-1.697 0L10 11.819l-2.651 3.029a1.2 1.2 0 1 1-1.697-1.697l2.758-3.15-2.759-3.152a1.2 1.2 0 1 1 1.697-1.697L10 8.183l2.651-3.031a1.2 1.2 0 1 1 1.697 1.697l-2.758 3.152 2.758 3.15a1.2 1.2 0 0 1 0 1.698z"/>
            </svg>
        </button>
    `;
    uploadStatus.appendChild(errorDiv);
    uploadStatus.style.display = 'block';
}

function showSuccess(message) {
    const successDiv = document.createElement('div');
    successDiv.className = 'bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded relative mb-4';
    successDiv.innerHTML = `
        <strong class="font-bold">Success! </strong>
        <span class="block sm:inline">${message}</span>
        <button class="absolute top-0 right-0 px-4 py-3" onclick="this.parentElement.remove()">
            <span class="sr-only">Dismiss</span>
            <svg class="h-4 w-4 fill-current" role="button" viewBox="0 0 20 20">
                <path d="M14.348 14.849a1.2 1.2 0 0 1-1.697 0L10 11.819l-2.651 3.029a1.2 1.2 0 1 1-1.697-1.697l2.758-3.15-2.759-3.152a1.2 1.2 0 1 1 1.697-1.697L10 8.183l2.651-3.031a1.2 1.2 0 1 1 1.697 1.697l-2.758 3.152 2.758 3.15a1.2 1.2 0 0 1 0 1.698z"/>
            </svg>
        </button>
    `;
    uploadStatus.appendChild(successDiv);
    uploadStatus.style.display = 'block';
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

function displayReceiptData(data) {
    // Clear previous data
    itemList.innerHTML = '';
    
    // Show receipt preview if available
    if (data.preview_url) {
        receiptPreview.src = data.preview_url;
        receiptPreview.style.display = 'block';
    }
    
    // Show confidence score
    if (data.confidence !== undefined) {
        const confidencePercent = Math.round(data.confidence * 100);
        confidenceDisplay.innerHTML = `
            <div class="flex items-center">
                <span class="mr-2">Confidence:</span>
                <div class="w-24 h-2 bg-gray-200 rounded">
                    <div class="h-2 bg-blue-500 rounded" style="width: ${confidencePercent}%"></div>
                </div>
                <span class="ml-2">${confidencePercent}%</span>
            </div>
        `;
        confidenceDisplay.style.display = 'block';
    }
    
    // Display items
    if (data.items && data.items.length > 0) {
        data.items.forEach((item, index) => {
            const row = document.createElement('tr');
            
            // Add warning class for suspicious items
            if (item.suspicious) {
                row.classList.add('bg-yellow-50');
            }
            
            row.innerHTML = `
                <td class="p-2 border">
                    <div class="flex items-center">
                        <input type="text" class="form-input w-full" value="${item.text}" 
                               data-original="${item.text}" ${item.confidence < 0.7 ? 'class="bg-yellow-50"' : ''}>
                        ${item.suspicious ? '<span class="ml-2 text-yellow-500">⚠️</span>' : ''}
                    </div>
                </td>
                <td class="p-2 border">
                    <input type="number" class="form-input w-20" value="${item.quantity || 1}" min="1"
                           data-original="${item.quantity}">
                </td>
                <td class="p-2 border">
                    <input type="number" class="form-input w-24" value="${item.price || 0}" step="0.01"
                           data-original="${item.price}">
                </td>
                <td class="p-2 border">
                    <div class="flex items-center space-x-2">
                        <button class="text-red-500 hover:text-red-700" onclick="removeItem(${index})">
                            <i class="fas fa-trash"></i>
                        </button>
                        ${item.confidence < 0.7 ? `
                            <span class="text-yellow-500" title="Low confidence: ${Math.round(item.confidence * 100)}%">
                                <i class="fas fa-exclamation-triangle"></i>
                            </span>
                        ` : ''}
                    </div>
                </td>
            `;
            
            itemList.appendChild(row);
        });
    } else {
        itemList.innerHTML = `
            <tr>
                <td colspan="4" class="p-4 text-center text-gray-500">
                    No items found. Add items manually.
                </td>
            </tr>
        `;
    }
    
    // Show totals
    if (data.total !== undefined) {
        totalDisplay.innerHTML = `
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700">Subtotal</label>
                    <input type="number" class="form-input mt-1" value="${data.subtotal || 0}" step="0.01">
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700">Tax</label>
                    <input type="number" class="form-input mt-1" value="${data.tax || 0}" step="0.01">
                </div>
                <div class="col-span-2">
                    <label class="block text-sm font-medium text-gray-700">Total</label>
                    <input type="number" class="form-input mt-1" value="${data.total}" step="0.01">
                </div>
            </div>
        `;
        totalDisplay.style.display = 'block';
    }
    
    // Show the modal
    receiptModal.style.display = 'block';
}

async function uploadReceipt(file) {
    if (isUploading) {
        showError('Another upload is in progress');
        return;
    }
    
    try {
        isUploading = true;
        currentProgress = 0;
        
        // Validate file
        if (!file || !file.type.startsWith('image/')) {
            showError('Please select a valid image file');
            return;
        }
        
        // Clear previous status
        uploadStatus.innerHTML = '';
        if (debugInfo) debugInfo.innerHTML = '';
        
        // Show processing overlay
        processingOverlay.innerHTML = `
            <div class="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center z-50">
                <div class="bg-white p-8 rounded-lg shadow-xl max-w-lg w-full">
                    <div class="flex flex-col items-center">
                        <div class="animate-spin rounded-full h-12 w-12 border-4 border-blue-500 border-t-transparent"></div>
                        <p class="mt-4 text-gray-700">Processing receipt...</p>
                        <div class="w-full mt-4">
                            <div class="h-2 bg-gray-200 rounded">
                                <div id="progress-bar" class="h-2 bg-blue-500 rounded transition-all duration-300" style="width: 0%"></div>
                            </div>
                        </div>
                        <p id="progress-status" class="mt-2 text-sm text-gray-600">Preparing upload...</p>
                    </div>
                </div>
            </div>
        `;
        processingOverlay.style.display = 'block';
        
        // Create FormData
        const formData = new FormData();
        formData.append('receipt_image', file);
        
        // Upload with progress tracking
        updateProgress(10, 'Starting upload...');
        
        const response = await fetch('/api/receipts/upload', {
            method: 'POST',
            body: formData
        });
        
        updateProgress(50, 'Processing receipt...');
        const result = await response.json();
        
        if (!response.ok || !result.success) {
            throw new Error(result.error || 'Upload failed');
        }
        
        updateProgress(80, 'Finalizing...');
        
        // Hide processing overlay
        processingOverlay.style.display = 'none';
        
        // Show success and display data
        showSuccess('Receipt uploaded successfully!');
        if (result.data) {
            displayReceiptData(result.data);
        }
        
        // Show debug info if available
        if (result.debug_info && debugInfo) {
            debugInfo.innerHTML = `
                <details class="mt-4 text-sm">
                    <summary class="cursor-pointer text-gray-600 hover:text-gray-800">
                        Debug Information
                    </summary>
                    <pre class="mt-2 p-4 bg-gray-50 rounded overflow-auto">${JSON.stringify(result.debug_info, null, 2)}</pre>
                </details>
            `;
            debugInfo.style.display = 'block';
        }
        
        updateProgress(100, 'Complete!');
        
    } catch (error) {
        console.error('Upload error:', error);
        showError('Failed to upload receipt', {
            message: error.message,
            stack: error.stack
        });
        
        // Hide processing overlay
        processingOverlay.style.display = 'none';
        
    } finally {
        isUploading = false;
    }
}

function updateProgress(percent, status) {
    currentProgress = percent;
    const progressBar = document.getElementById('progress-bar');
    const progressStatus = document.getElementById('progress-status');
    
    if (progressBar && progressStatus) {
        progressBar.style.width = `${percent}%`;
        progressStatus.textContent = status;
    }
}

// Drag and drop handling
const dropZone = document.getElementById('drop-zone');

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('border-blue-500', 'bg-blue-50');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('border-blue-500', 'bg-blue-50');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('border-blue-500', 'bg-blue-50');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        uploadReceipt(files[0]);
    }
});

// File input handling
const fileInput = document.getElementById('receipt-file');

fileInput.addEventListener('change', (e) => {
    const files = e.target.files;
    if (files.length > 0) {
        uploadReceipt(files[0]);
    }
});

// Item management
function removeItem(index) {
    const row = itemList.children[index];
    if (row) {
        row.remove();
        updateTotals();
    }
}

function addNewItem() {
    const row = document.createElement('tr');
    row.className = 'hover:bg-gray-50';
    row.innerHTML = `
        <td class="p-2 border">
            <input type="text" class="form-input w-full" placeholder="Item description">
        </td>
        <td class="p-2 border">
            <input type="number" class="form-input w-20" value="1" min="1">
        </td>
        <td class="p-2 border">
            <input type="number" class="form-input w-24" value="0" step="0.01">
        </td>
        <td class="p-2 border">
            <button class="text-red-500 hover:text-red-700" onclick="this.closest('tr').remove(); updateTotals();">
                <i class="fas fa-trash"></i>
            </button>
        </td>
    `;
    itemList.appendChild(row);
}

function updateTotals() {
    const items = Array.from(itemList.children).map(row => {
        const inputs = row.querySelectorAll('input');
        return {
            quantity: parseFloat(inputs[1].value) || 0,
            price: parseFloat(inputs[2].value) || 0
        };
    });
    
    const subtotal = items.reduce((sum, item) => sum + (item.quantity * item.price), 0);
    const taxInput = document.querySelector('#total-display input[name="tax"]');
    const tax = parseFloat(taxInput.value) || 0;
    const total = subtotal + tax;
    
    document.querySelector('#total-display input[name="subtotal"]').value = subtotal.toFixed(2);
    document.querySelector('#total-display input[name="total"]').value = total.toFixed(2);
}

// Save receipt data
async function saveReceiptData() {
    try {
        // Show saving indicator
        const saveBtn = document.getElementById('save-button');
        const originalText = saveBtn.innerHTML;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
        saveBtn.disabled = true;
        
        // Collect data
        const items = Array.from(itemList.children).map(row => {
            const inputs = row.querySelectorAll('input');
            return {
                name: inputs[0].value,
                quantity: parseFloat(inputs[1].value) || 1,
                price: parseFloat(inputs[2].value) || 0
            };
        });
        
        const totals = {
            subtotal: parseFloat(document.querySelector('#total-display input[name="subtotal"]').value) || 0,
            tax: parseFloat(document.querySelector('#total-display input[name="tax"]').value) || 0,
            total: parseFloat(document.querySelector('#total-display input[name="total"]').value) || 0
        };
        
        // Validate data
        if (items.length === 0) {
            throw new Error('Receipt must have at least one item');
        }
        
        if (totals.total <= 0) {
            throw new Error('Total amount must be greater than zero');
        }
        
        // Send request
        const response = await fetch('/api/receipts/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                items,
                ...totals
            })
        });
        
        const result = await response.json();
        
        if (!response.ok || !result.success) {
            throw new Error(result.error || 'Failed to save receipt data');
        }
        
        showSuccess('Receipt data saved successfully!');
        receiptModal.style.display = 'none';
        
    } catch (error) {
        console.error('Save error:', error);
        showError(error.message);
        
    } finally {
        // Restore save button
        const saveBtn = document.getElementById('save-button');
        saveBtn.innerHTML = originalText;
        saveBtn.disabled = false;
    }
} 