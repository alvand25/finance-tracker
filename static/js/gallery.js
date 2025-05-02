// Filter functionality
document.addEventListener('DOMContentLoaded', function() {
    const statusFilter = document.getElementById('statusFilter');
    const storeFilter = document.getElementById('storeFilter');
    
    if (statusFilter && storeFilter) {
        statusFilter.addEventListener('change', filterReceipts);
        storeFilter.addEventListener('change', filterReceipts);
    }
});

function filterReceipts() {
    const statusFilter = document.getElementById('statusFilter').value;
    const storeFilter = document.getElementById('storeFilter').value;
    
    document.querySelectorAll('.receipt-card').forEach(card => {
        const status = card.dataset.status;
        const store = card.dataset.store;
        
        const statusMatch = statusFilter === 'all' || status === statusFilter;
        const storeMatch = storeFilter === 'all' || store === storeFilter;
        
        card.style.display = statusMatch && storeMatch ? 'block' : 'none';
    });
} 