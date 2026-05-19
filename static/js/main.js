console.log("JS WORKING ✅");

document.addEventListener('DOMContentLoaded', function () {

    // Chatbot elements
    const chatWidget = document.getElementById('chatbot-widget');
    const chatToggleBtn = document.getElementById('chat-toggle-btn');
    const closeChatBtn = document.getElementById('close-chat');
    const chatBody = document.getElementById('chat-body');
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');

    // =========================
    // فتح / إغلاق الشات
    // =========================
    chatToggleBtn.addEventListener('click', () => {
        chatWidget.style.display = 'flex';
        chatToggleBtn.style.display = 'none';
    });

    closeChatBtn.addEventListener('click', () => {
        chatWidget.style.display = 'none';
        chatToggleBtn.style.display = 'flex';
    });

    // =========================
    // 🎯 Animation (scroll)
    // =========================
    let scrollTimeout = null;
    let idleTimeout = null;
    let lastScrollY = window.scrollY;

    setTimeout(() => {
        chatToggleBtn.classList.add('idle-float');
    }, 800);

    window.addEventListener('scroll', () => {
        const currentScrollY = window.scrollY;
        const scrollDelta = Math.abs(currentScrollY - lastScrollY);

        if (scrollDelta > 5) {
            chatToggleBtn.classList.remove('idle-float');

            chatToggleBtn.classList.remove('scroll-bounce');
            void chatToggleBtn.offsetWidth;
            chatToggleBtn.classList.add('scroll-bounce');

            const direction = currentScrollY > lastScrollY ? 1 : -1;
            const shift = Math.min(scrollDelta * 0.15, 12) * direction;
            chatToggleBtn.style.transform = `translateY(${shift}px)`;

            clearTimeout(scrollTimeout);
            clearTimeout(idleTimeout);

            scrollTimeout = setTimeout(() => {
                chatToggleBtn.style.transform = '';
                chatToggleBtn.classList.remove('scroll-bounce');

                idleTimeout = setTimeout(() => {
                    chatToggleBtn.classList.add('idle-float');
                }, 600);
            }, 200);
        }

        lastScrollY = currentScrollY;
    });

    // =========================
    // 🧠 إضافة رسالة
    // =========================
    function addMessage(message, isUser) {
        const div = document.createElement('div');
        div.classList.add('chat-message');
        div.classList.add(isUser ? 'user-message' : 'bot-message');
        div.textContent = message;
        chatBody.appendChild(div);
        chatBody.scrollTop = chatBody.scrollHeight;
    }

    function addHTMLMessage(html) {
        const div = document.createElement('div');
        div.classList.add('chat-message', 'bot-message');
        div.style.padding = '0';
        div.style.background = 'transparent';
        div.style.maxWidth = '100%';
        div.innerHTML = html;
        chatBody.appendChild(div);
        chatBody.scrollTop = chatBody.scrollHeight;
    }

    // =========================
    // ❤️ Chat Favorite Toggle
    // =========================
    window.chatToggleFav = function(propId, btn) {
        fetch(`/favorite/${propId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'same-origin'
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'added') {
                btn.classList.add('fav-active');
                btn.innerHTML = '❤️';
            } else {
                btn.classList.remove('fav-active');
                btn.innerHTML = '🤍';
            }
        })
        .catch(() => addMessage("⚠️ Login required to save favorites", false));
    };

    // =========================
    // 💬 Chat Contact Agent
    // =========================
    window.chatContactAgent = function(agentId, propTitle) {
        const msg = prompt(`Send message to agent about "${propTitle}":`);
        if (!msg) return;
        fetch('/api/send_message', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'same-origin',
            body: JSON.stringify({agent_id: agentId, message: msg})
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'sent') {
                addMessage("✅ Message sent to agent!", false);
            } else {
                addMessage("⚠️ " + (data.error || "Login required"), false);
            }
        })
        .catch(() => addMessage("⚠️ Login required to contact agents", false));
    };

    // =========================
    // 🚀 sendMessage
    // =========================
    function sendMessage() {
        const message = chatInput.value.trim();

        if (!message) return;

        addMessage(message, true);
        chatInput.value = '';

        // Show typing indicator
        const typingDiv = document.createElement('div');
        typingDiv.classList.add('chat-message', 'bot-message');
        typingDiv.id = 'typing-indicator';
        typingDiv.innerHTML = '<div style="display:flex;gap:4px;padding:4px 0;"><span style="animation:blink 1s infinite;font-size:1.3em;">●</span><span style="animation:blink 1s 0.2s infinite;font-size:1.3em;">●</span><span style="animation:blink 1s 0.4s infinite;font-size:1.3em;">●</span></div>';
        chatBody.appendChild(typingDiv);
        chatBody.scrollTop = chatBody.scrollHeight;

        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ 
                message: message, 
                conversation_id: window._currentConversationId || null 
            })
        })
        .then(response => {
            if (response.status === 429) {
                const ti = document.getElementById('typing-indicator');
                if (ti) ti.remove();
                addMessage("⚠️ Too many messages — please wait a minute.", false);
                throw new Error('rate_limited');
            }
            return response.json();
        })
        .then(data => {
            // Remove typing indicator
            const ti = document.getElementById('typing-indicator');
            if (ti) ti.remove();

            console.log("Response:", data);

            // Save conversation_id for memory
            if (data.conversation_id) {
                window._currentConversationId = data.conversation_id;
            }

            // Handle action-only responses (favorite/contact)
            if (data.action) {
                if (data.action === 'add_favorite') {
                    addMessage("❤️ Property saved to favorites!", false);
                } else if (data.action === 'send_message') {
                    addMessage("✅ Message sent to agent!", false);
                }
                return;
            }

            // AI text reply
            const reply = data.text ? data.text : "مافهمت، جرب تكتب بشكل اوضح 😊";
            addMessage(reply, false);

            // 🏠 Property Cards
            if (data.properties && data.properties.length > 0) {
                data.properties.forEach(p => {
                    const priceFormatted = (p.price || 0).toLocaleString(undefined, {maximumFractionDigits: 0});
                    const yearlyFormatted = (p.yearly_income || 0).toLocaleString(undefined, {maximumFractionDigits: 0});
                    const p1yFormatted = (p.price_1y || 0).toLocaleString(undefined, {maximumFractionDigits: 0});
                    const p2yFormatted = (p.price_2y || 0).toLocaleString(undefined, {maximumFractionDigits: 0});
                    const p5yFormatted = (p.price_5y || 0).toLocaleString(undefined, {maximumFractionDigits: 0});
                    const safeTitle = (p.title || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
                    const isNew = p.is_new ? '<span style="background:#E53935;color:#fff;padding:2px 8px;border-radius:6px;font-size:0.68em;font-weight:700;margin-right:4px;">🔥 New</span>' : '';
                    const statusBadge = p.status === 'under_construction' ? '<span style="background:#FF9800;color:#fff;padding:2px 8px;border-radius:6px;font-size:0.68em;font-weight:600;">🏗️ Under Construction</span>' : '';

                    const cardHTML = `
                    <div style="background:#FFFBF5;border:1px solid #E8D5C0;border-radius:12px;padding:14px;margin:6px 0;font-size:0.85em;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
                        <div style="margin-bottom:6px;">${isNew}${statusBadge}</div>
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                            <div style="flex:1;">
                                <div style="font-weight:700;color:#3E2723;font-size:0.95em;">${p.title}</div>
                                <div style="color:#8D6E63;font-size:0.8em;margin-top:2px;"><i class="fas fa-map-marker-alt"></i> ${p.location}</div>
                            </div>
                            <div style="text-align:right;">
                                <div style="font-weight:700;color:#B8860B;font-size:1.05em;">OMR ${priceFormatted}</div>
                                <div style="color:#2E7D32;font-size:0.75em;font-weight:600;">ROI ${p.roi || 0}%</div>
                            </div>
                        </div>
                        <div style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap;">
                            <span style="background:#E8F5E9;color:#2E7D32;padding:3px 8px;border-radius:6px;font-size:0.72em;font-weight:600;">💰 ${yearlyFormatted}/yr</span>
                            <span style="background:#E3F2FD;color:#1565C0;padding:3px 8px;border-radius:6px;font-size:0.72em;font-weight:600;">📈 1Y: ${p1yFormatted}</span>
                            <span style="background:#F3E5F5;color:#6A1B9A;padding:3px 8px;border-radius:6px;font-size:0.72em;font-weight:600;">📊 2Y: ${p2yFormatted}</span>
                            <span style="background:#FFF3E0;color:#E65100;padding:3px 8px;border-radius:6px;font-size:0.72em;font-weight:600;">🚀 5Y: ${p5yFormatted}</span>
                        </div>
                        ${p.reason ? `<div style="color:#5D4037;font-size:0.75em;margin-top:8px;font-style:italic;">💡 ${p.reason}</div>` : ''}
                        ${p.status === 'under_construction' ? `<div style="background:#FFF8E1;color:#F57F17;font-size:0.73em;margin-top:6px;padding:6px 10px;border-radius:8px;border:1px solid #FFE082;">⚠️ This project is under construction — early investment advantage with higher ROI</div>` : ''}
                        <div style="display:flex;gap:6px;margin-top:10px;border-top:1px solid #E8D5C0;padding-top:10px;">
                            <button onclick="chatToggleFav(${p.id}, this)" style="flex:1;background:#FFF3E0;color:#E65100;border:none;border-radius:8px;padding:6px;font-size:0.78em;font-weight:600;cursor:pointer;">🤍 Save</button>
                            <button onclick="chatContactAgent(${p.agent_id}, '${safeTitle}')" style="flex:1;background:#E8F5E9;color:#2E7D32;border:none;border-radius:8px;padding:6px;font-size:0.78em;font-weight:600;cursor:pointer;">💬 Contact</button>
                        </div>
                        <div style="font-size:0.7em;color:#8D6E63;margin-top:6px;">Agent: ${p.agent || 'N/A'}</div>
                    </div>`;
                    addHTMLMessage(cardHTML);
                });
            }

            // 🔥 Investment Hotspots
            if (data.investment_hotspots && data.investment_hotspots.length > 0) {
                let hotspotsHTML = '<div style="background:linear-gradient(135deg,#FFF8E1,#FFF3E0);border:1px solid #FFE0B2;border-radius:12px;padding:12px;margin:6px 0;">';
                hotspotsHTML += '<div style="font-weight:700;color:#E65100;font-size:0.88em;margin-bottom:8px;">🔥 Investment Hotspots</div>';
                data.investment_hotspots.forEach(h => {
                    hotspotsHTML += `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #FFE0B2;">
                        <div>
                            <div style="font-weight:600;font-size:0.82em;color:#3E2723;">${h.name}</div>
                            <div style="font-size:0.72em;color:#6D4C41;">${h.reason}</div>
                        </div>
                    </div>`;
                });
                hotspotsHTML += '</div>';
                addHTMLMessage(hotspotsHTML);
            }

        })
        .catch(error => {
            if (error.message === 'rate_limited') return;
            const ti = document.getElementById('typing-indicator');
            if (ti) ti.remove();
            console.error('Error:', error);
            addMessage("⚠️ صار خطأ في الاتصال بالسيرفر", false);
        });
    }

    // =========================
    // 🎮 Events
    // =========================
    sendBtn.addEventListener('click', sendMessage);

    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    // =========================
    // 🗺️ Map Focus Helper
    // =========================
    window.focusMap = function(lat, lng, title, price, roi) {
        if (typeof map !== "undefined" && map) {
            const popupContent = `<div class="p-1">
                <h6 class="fw-bold mb-1">${title}</h6>
                <div class="small">Price: OMR ${price.toLocaleString(undefined, {maximumFractionDigits: 0})}</div>
                <div class="small text-success fw-bold">ROI: ${roi}%</div>
            </div>`;
            L.marker([lat, lng])
                .addTo(map)
                .bindPopup(popupContent)
                .openPopup();
            map.flyTo([lat, lng], 15, {
                animate: true,
                duration: 1.5
            });
            // Minimize chat slightly on mobile to see map
            if (window.innerWidth < 768) {
                closeChatBtn.click();
            }
        } else {
            // Redirect to investment map with query params using safe fallback
            window.location.href = `/investment-map?lat=${lat}&lng=${lng}`;
        }
    };

    // =========================
    // 📊 Price Prediction (handled inline in home.html)
    // =========================

    // =========================
    // Load user favorite IDs 
    // =========================
    fetch('/api/favorites', {credentials: 'same-origin'})
    .then(r => {
        if (r.redirected || r.status === 302 || r.status === 401) {
            window._userFavIds = [];
            return null;
        }
        return r.json();
    })
    .then(data => {
        if (data) {
            window._userFavIds = data.favorite_ids || [];
        }
    })
    .catch(() => { window._userFavIds = []; });

});

// Typing animation keyframes
const style = document.createElement('style');
style.textContent = `@keyframes blink { 0%,100%{opacity:0.2} 50%{opacity:1} }`;
document.head.appendChild(style);