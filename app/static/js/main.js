// Premium micro-interactions and link copying utilities
document.addEventListener('DOMContentLoaded', () => {
    // Copy Link function
    const copyBtn = document.getElementById('btn-copy-link');
    if (copyBtn) {
        copyBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            const shareUrl = copyBtn.getAttribute('data-url');
            if (!shareUrl) return;

            try {
                await navigator.clipboard.writeText(shareUrl);
                const originalText = copyBtn.innerHTML;
                
                // Show success feedback
                copyBtn.innerHTML = '✨ Link Copied!';
                copyBtn.style.background = 'linear-gradient(135deg, #10B981 0%, #059669 100%)'; // Emerald Green
                copyBtn.style.boxShadow = '0 4px 20px rgba(16, 185, 129, 0.4)';
                
                // Reset after 2 seconds
                setTimeout(() => {
                    copyBtn.innerHTML = originalText;
                    copyBtn.style.background = '';
                    copyBtn.style.boxShadow = '';
                }, 2000);
            } catch (err) {
                console.error('Failed to copy: ', err);
                alert('Could not copy link. Manually copy: ' + shareUrl);
            }
        });
    }

    // Add glowing hover coordinates to glass card
    const card = document.querySelector('.glass-card');
    if (card) {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            // Set custom properties for highlight coordinates
            card.style.setProperty('--mouse-x', `${x}px`);
            card.style.setProperty('--mouse-y', `${y}px`);
        });
    }
});
