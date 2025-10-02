class RestaurantChatApp {
    constructor() {
        this.apiBaseUrl = window.location.origin;
        this.threadId = null;
        this.isConnected = false;
        this.isTyping = false;
        
        this.initializeElements();
        this.attachEventListeners();
        this.checkApiHealth();
        this.initializeChat();
    }

    initializeElements() {
        // Chat elements
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.chatMessages = document.getElementById('chatMessages');
        this.typingIndicator = document.getElementById('typingIndicator');
        this.charCount = document.getElementById('charCount');
        
        // Status elements
        this.connectionStatus = document.getElementById('connectionStatus');
        this.statusText = document.getElementById('statusText');
        this.agentStatus = document.getElementById('agentStatus');
        
        // Action buttons
        this.clearChatBtn = document.getElementById('clearChat');
        this.exportChatBtn = document.getElementById('exportChat');
        
        // Loading overlay
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.toastContainer = document.getElementById('toastContainer');
    }

    attachEventListeners() {
        // Send message events
        this.sendButton.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Input events
        this.messageInput.addEventListener('input', () => this.handleInputChange());
        this.messageInput.addEventListener('focus', () => this.autoResizeTextarea());
        
        // Action buttons
        this.clearChatBtn.addEventListener('click', () => this.clearChat());
        this.exportChatBtn.addEventListener('click', () => this.exportChat());
        
        // Window events
        window.addEventListener('beforeunload', () => this.cleanup());
    }

    async checkApiHealth() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/health`);
            const data = await response.json();
            
            if (data.status === 'healthy') {
                this.setConnectionStatus(true, 'Connected');
                this.hideLoadingOverlay();
            } else {
                throw new Error('API unhealthy');
            }
        } catch (error) {
            console.error('API health check failed:', error);
            this.setConnectionStatus(false, 'Connection Failed');
            this.showToast('Failed to connect to AI agent. Please refresh the page.', 'error');
            this.hideLoadingOverlay();
        }
    }

    setConnectionStatus(connected, statusText) {
        this.isConnected = connected;
        this.connectionStatus.className = `status-dot ${connected ? 'online' : 'offline'}`;
        this.statusText.textContent = statusText;
        this.agentStatus.textContent = connected ? 
            'Ready to help with bookings and questions' : 
            'Connection lost - trying to reconnect...';
    }

    initializeChat() {
        // Generate a unique thread ID for this session
        this.threadId = 'web-demo-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        this.hideLoadingOverlay();
    }

    handleInputChange() {
        const value = this.messageInput.value;
        const length = value.length;
        
        // Update character count
        this.charCount.textContent = length;
        
        // Enable/disable send button
        this.sendButton.disabled = !value.trim() || !this.isConnected || this.isTyping;
        
        // Auto-resize textarea
        this.autoResizeTextarea();
        
        // Update send button icon based on state
        const icon = this.sendButton.querySelector('i');
        if (this.isTyping) {
            icon.className = 'fas fa-spinner fa-spin';
        } else {
            icon.className = 'fas fa-paper-plane';
        }
    }

    autoResizeTextarea() {
        this.messageInput.style.height = 'auto';
        this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 120) + 'px';
    }

    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || !this.isConnected || this.isTyping) return;

        // Add user message to chat
        this.addMessage('user', message);
        
        // Clear input and reset
        this.messageInput.value = '';
        this.handleInputChange();
        
        // Show typing indicator
        this.setTypingState(true);
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    thread_id: this.threadId
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            // Update thread ID if provided
            if (data.thread_id) {
                this.threadId = data.thread_id;
            }
            
            // Add agent response to chat
            this.addMessage('agent', data.response);
            
        } catch (error) {
            console.error('Error sending message:', error);
            this.addMessage('system', 
                `❌ Sorry, I encountered an error: ${error.message}. Please try again or refresh the page.`
            );
            this.showToast('Failed to send message. Please try again.', 'error');
        } finally {
            this.setTypingState(false);
        }
    }

    setTypingState(typing) {
        this.isTyping = typing;
        this.typingIndicator.style.display = typing ? 'flex' : 'none';
        this.handleInputChange(); // Update button state
        
        if (typing) {
            this.scrollToBottom();
        }
    }

    addMessage(sender, content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        
        const timestamp = new Date().toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit'
        });

        let avatarIcon, senderName, messageClass;
        
        switch (sender) {
            case 'user':
                avatarIcon = 'fas fa-user';
                senderName = 'You';
                messageClass = 'user';
                break;
            case 'agent':
                avatarIcon = 'fas fa-robot';
                senderName = 'AI Assistant';
                messageClass = 'agent';
                break;
            case 'system':
                avatarIcon = 'fas fa-exclamation-triangle';
                senderName = 'System';
                messageClass = 'system';
                break;
        }

        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="${avatarIcon}"></i>
            </div>
            <div class="message-content">
                <div class="message-header">
                    <span class="sender-name">${senderName}</span>
                    <span class="message-time">${timestamp}</span>
                </div>
                <div class="message-text">${this.formatMessage(content)}</div>
            </div>
        `;

        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        
        // Animate in
        requestAnimationFrame(() => {
            messageDiv.style.opacity = '1';
            messageDiv.style.transform = 'translateY(0)';
        });
    }

    formatMessage(text) {
        // Convert markdown-like formatting to HTML
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/```(.*?)```/gs, '<pre><code>$1</code></pre>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>')
            .replace(/(\d+\.\s)/g, '<br>$1') // Better list formatting
            .replace(/(•\s)/g, '<br>$1'); // Better bullet formatting
    }

    scrollToBottom() {
        requestAnimationFrame(() => {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        });
    }

    clearChat() {
        // Remove all messages except welcome message
        const messages = this.chatMessages.querySelectorAll('.message');
        messages.forEach(msg => msg.remove());
        
        // Generate new thread ID
        this.threadId = 'web-demo-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        
        this.showToast('Chat cleared! Starting a new conversation.', 'success');
    }

    exportChat() {
        const messages = this.chatMessages.querySelectorAll('.message');
        let exportText = `Restaurant AI Agent Chat Export\nDate: ${new Date().toLocaleString()}\nThread ID: ${this.threadId}\n\n`;
        
        messages.forEach(msg => {
            const sender = msg.querySelector('.sender-name').textContent;
            const time = msg.querySelector('.message-time').textContent;
            const content = msg.querySelector('.message-text').textContent;
            exportText += `[${time}] ${sender}: ${content}\n\n`;
        });
        
        const blob = new Blob([exportText], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `restaurant-chat-${Date.now()}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        this.showToast('Chat exported successfully!', 'success');
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const icon = type === 'error' ? 'fas fa-exclamation-circle' : 
                    type === 'success' ? 'fas fa-check-circle' : 
                    'fas fa-info-circle';
        
        toast.innerHTML = `
            <i class="${icon}"></i>
            <span>${message}</span>
        `;
        
        this.toastContainer.appendChild(toast);
        
        // Animate in
        requestAnimationFrame(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateX(0)';
        });
        
        // Remove after 5 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 5000);
    }

    hideLoadingOverlay() {
        setTimeout(() => {
            this.loadingOverlay.style.opacity = '0';
            setTimeout(() => {
                this.loadingOverlay.style.display = 'none';
            }, 300);
        }, 1000);
    }

    cleanup() {
        // Cleanup when page is about to unload
        console.log('Cleaning up chat session');
    }
}

// Global functions for sample prompts
window.sendSamplePrompt = function(prompt) {
    const app = window.chatApp;
    if (app && app.isConnected && !app.isTyping) {
        app.messageInput.value = prompt;
        app.handleInputChange();
        app.sendMessage();
    }
};

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.chatApp = new RestaurantChatApp();
});

// Handle visibility change to potentially reconnect
document.addEventListener('visibilitychange', () => {
    if (!document.hidden && window.chatApp && !window.chatApp.isConnected) {
        setTimeout(() => {
            window.chatApp.checkApiHealth();
        }, 1000);
    }
});