const chatInput = document.getElementById("chatInput");
const sendButton = document.getElementById("sendButton");
const chatContainer = document.getElementById("chatContainer");
const welcomeMessage = document.getElementById("welcomeMessage");
const welcomeInput = document.getElementById("welcomeInput");
const welcomeSendButton = document.getElementById("welcomeSendButton");
const messages = document.getElementById("messages");
const panel = document.getElementById("appPanel");
const panelTitle = document.getElementById("panelTitle");
const panelSubtitle = document.getElementById("panelSubtitle");
const panelBody = document.getElementById("panelBody");
const panelClose = document.getElementById("panelClose");
const voiceMode = document.getElementById("voiceMode");
const CHAT_CACHE_KEY = "vozSeguraChats";
const ACTIVE_CHAT_COOKIE = "voz_segura_active_chat";
const COMPOSE_MODE_COOKIE = "voz_segura_compose_mode";

let mediaRecorder;
let audioChunks = [];
let recognition;
let activeChatId = getCookie(ACTIVE_CHAT_COOKIE) || createChatId();
let activeComposeMode = getCookie(COMPOSE_MODE_COOKIE) || "chat";

function setCookie(name, value, days = 30) {
    const maxAge = days * 24 * 60 * 60;
    document.cookie = `${name}=${encodeURIComponent(value)}; max-age=${maxAge}; path=/; samesite=lax`;
}

function getCookie(name) {
    const found = document.cookie.split("; ").find(row => row.startsWith(`${name}=`));
    return found ? decodeURIComponent(found.split("=")[1]) : "";
}

function createChatId() {
    const id = `chat_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    setCookie(ACTIVE_CHAT_COOKIE, id);
    return id;
}

function getChats() {
    try {
        return JSON.parse(localStorage.getItem(CHAT_CACHE_KEY) || "[]");
    } catch {
        return [];
    }
}

function saveChats(chats) {
    localStorage.setItem(CHAT_CACHE_KEY, JSON.stringify(chats.slice(0, 30)));
}

function getActiveChat() {
    const chats = getChats();
    let chat = chats.find(item => item.id === activeChatId);
    if (!chat) {
        chat = { id: activeChatId, title: "Nuevo chat", createdAt: Date.now(), updatedAt: Date.now(), messages: [] };
        chats.unshift(chat);
        saveChats(chats);
    }
    return chat;
}

function updateActiveChat(updater) {
    const chats = getChats();
    let index = chats.findIndex(item => item.id === activeChatId);
    if (index < 0) {
        chats.unshift({ id: activeChatId, title: "Nuevo chat", createdAt: Date.now(), updatedAt: Date.now(), messages: [] });
        index = 0;
    }
    updater(chats[index]);
    chats[index].updatedAt = Date.now();
    saveChats([chats[index], ...chats.filter((_, i) => i !== index)]);
    renderHistory();
}

function updateChatView() {
    const hasMessages = messages.children.length > 0;
    const chatInputContainer = chatContainer.querySelector(".input-container") || chatContainer.querySelector(".chat-input");

    document.body.classList.toggle("has-messages", hasMessages);
    if (welcomeMessage) welcomeMessage.style.display = hasMessages ? "none" : "flex";
    chatContainer.style.display = hasMessages ? "flex" : "none";
    if (chatInputContainer) {
        const mode = chatInputContainer.classList.contains("chat-input") ? "flex" : "grid";
        chatInputContainer.style.display = hasMessages ? mode : "none";
    }
    messages.style.display = hasMessages ? "flex" : "none";
}

function scrollChatToBottom() {
    if (!messages || !chatContainer) return;
    messages.scrollTop = messages.scrollHeight;
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function plainTextFromHtml(html) {
    const div = document.createElement("div");
    div.innerHTML = html || "";
    return div.textContent || div.innerText || "";
}

function escapeHtml(text) {
    return (text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function sanitizeHref(href) {
    const url = (href || "").trim();
    if (!url) return "#";
    if (/^(https?:\/\/|\/)/i.test(url)) return url;
    return "#";
}

function linkClassForHref(href) {
    if (href === "/download_form") return "btn btn-primary mt-2";
    if (href === "/download_sue") return "btn btn-success mt-2";
    return "text-primary";
}

function renderInlineMarkdown(text) {
    let output = escapeHtml(text || "");

    output = output.replace(/`([^`]+)`/g, (_, code) => `<code>${escapeHtml(code)}</code>`);
    output = output.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    output = output.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    output = output.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) => {
        const safeHref = sanitizeHref(href);
        const cls = linkClassForHref(safeHref);
        const target = safeHref.startsWith("/") ? "_self" : "_blank";
        return `<a href="${safeHref}" target="${target}" class="${cls}">${label}</a>`;
    });

    return output;
}

function markdownToHtml(text) {
    const source = (text || "").replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
    if (!source) return "";

    const codeBlocks = [];
    const placeholderPrefix = "__CODE_BLOCK_";
    const withPlaceholders = source.replace(/```([a-zA-Z0-9_-]*)\n?([\s\S]*?)```/g, (_, lang, code) => {
        const language = (lang || "").trim();
        const escapedCode = escapeHtml(code.replace(/\n$/, ""));
        const block = `<pre><code${language ? ` class="language-${language}"` : ""}>${escapedCode}</code></pre>`;
        const token = `${placeholderPrefix}${codeBlocks.length}__`;
        codeBlocks.push(block);
        return token;
    });

    const lines = withPlaceholders.split("\n");
    const html = [];
    let i = 0;

    while (i < lines.length) {
        const line = lines[i].trimEnd();
        const trimmed = line.trim();

        if (!trimmed) {
            i += 1;
            continue;
        }

        if (trimmed.startsWith(placeholderPrefix)) {
            const index = Number(trimmed.replace(placeholderPrefix, "").replace("__", ""));
            html.push(codeBlocks[index] || "");
            i += 1;
            continue;
        }

        const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
        if (headingMatch) {
            const level = headingMatch[1].length;
            html.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
            i += 1;
            continue;
        }

        if (/^[-*]\s+/.test(trimmed)) {
            const items = [];
            while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
                items.push(lines[i].replace(/^\s*[-*]\s+/, "").trim());
                i += 1;
            }
            html.push(`<ul>${items.map(item => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ul>`);
            continue;
        }

        if (/^\d+\.\s+/.test(trimmed)) {
            const items = [];
            while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
                items.push(lines[i].replace(/^\s*\d+\.\s+/, "").trim());
                i += 1;
            }
            html.push(`<ol>${items.map(item => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ol>`);
            continue;
        }

        if (/^>\s?/.test(trimmed)) {
            const quote = [];
            while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
                quote.push(lines[i].replace(/^\s*>\s?/, "").trim());
                i += 1;
            }
            html.push(`<blockquote>${renderInlineMarkdown(quote.join(" "))}</blockquote>`);
            continue;
        }

        const paragraph = [];
        while (i < lines.length) {
            const candidate = lines[i].trim();
            if (!candidate) break;
            if (candidate.startsWith(placeholderPrefix) || /^(#{1,4})\s+/.test(candidate) || /^[-*]\s+/.test(candidate) || /^\d+\.\s+/.test(candidate) || /^>\s?/.test(candidate)) {
                break;
            }
            paragraph.push(candidate);
            i += 1;
        }
        html.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
    }

    return html.join("\n");
}

function looksLikeHtml(text) {
    const value = (text || "").trim();
    if (!value) return false;
    return /<\/?[a-z][\s\S]*>/i.test(value);
}

function sanitizeServerHtml(html) {
    const template = document.createElement("template");
    template.innerHTML = html || "";

    const allowedTags = new Set([
        "P", "BR", "STRONG", "EM", "B", "I", "U", "UL", "OL", "LI",
        "A", "CODE", "PRE", "BLOCKQUOTE", "H1", "H2", "H3", "H4", "SPAN"
    ]);

    const walk = node => {
        if (node.nodeType === Node.ELEMENT_NODE) {
            const tag = node.tagName;
            if (!allowedTags.has(tag)) {
                const textNode = document.createTextNode(node.textContent || "");
                node.replaceWith(textNode);
                return;
            }

            // Limpiar atributos peligrosos.
            [...node.attributes].forEach(attr => {
                const name = attr.name.toLowerCase();
                const value = attr.value || "";
                if (name.startsWith("on")) {
                    node.removeAttribute(attr.name);
                    return;
                }

                if (tag === "A" && name === "href") {
                    if (!/^(https?:\/\/|\/)/i.test(value.trim())) {
                        node.setAttribute("href", "#");
                    }
                    if (!node.hasAttribute("target")) {
                        node.setAttribute("target", value.startsWith("/") ? "_self" : "_blank");
                    }
                    node.setAttribute("rel", "noopener noreferrer");
                    return;
                }

                if (name !== "href" && name !== "target" && name !== "rel" && name !== "class") {
                    node.removeAttribute(attr.name);
                }
            });
        }

        [...node.childNodes].forEach(walk);
    };

    [...template.content.childNodes].forEach(walk);
    return template.innerHTML;
}

function normalizeBotResponse(botResponse) {
    let response = botResponse || "";
    if (response.includes("✅ La denuncia ha sido generada correctamente.") || response.includes("La denuncia ha sido generada correctamente")) {
        response = response.replace("/download_sue", "[Descargar denuncia](/download_sue)");
    }

    if (looksLikeHtml(response)) {
        return sanitizeServerHtml(response);
    }

    return markdownToHtml(response);
}

function getCurrentDraft() {
    const isWelcomeVisible = welcomeMessage && window.getComputedStyle(welcomeMessage).display !== "none";
    return isWelcomeVisible ? welcomeInput : chatInput;
}

function setComposeMode(mode) {
    activeComposeMode = mode;
    setCookie(COMPOSE_MODE_COOKIE, mode);
    updateModeButtons();
}

function updateModeButtons() {
    document.querySelectorAll("[data-tool='search'], [data-tool='reason']").forEach(button => {
        const isActive = button.dataset.tool === activeComposeMode;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
    });

    const placeholders = {
        chat: "Pregunta lo que quieras",
        search: "Busca en chats y documentos",
        reason: "Pregunta algo para analizar con cuidado",
    };
    if (welcomeInput) welcomeInput.placeholder = placeholders[activeComposeMode] || placeholders.chat;
    if (chatInput) chatInput.placeholder = placeholders[activeComposeMode] || placeholders.chat;
}

function buildOutgoingText(text) {
    if (activeComposeMode === "search") {
        return `Busca información relevante en la biblioteca, el historial y el contexto disponible. Responde de forma clara y cita cuando la información provenga de documentos. Recuerda indicar que la información importante debe verificarse.\n\nConsulta: ${text}`;
    }

    if (activeComposeMode === "reason") {
        return `Analiza esta consulta con cuidado antes de responder. Explica los pasos importantes, señala supuestos o dudas, evita inventar datos y recuerda que la información importante debe verificarse.\n\nConsulta: ${text}`;
    }

    return text;
}

function appendMessage(role, content, html = null, persist = true) {
    const node = document.createElement("div");
    node.classList.add("message", role === "user" ? "user-message" : "bot-message");
    if (html) {
        node.innerHTML = html;
    } else {
        node.textContent = content;
    }
    messages.appendChild(node);
    scrollChatToBottom();
    updateChatView();

    if (persist) {
        updateActiveChat(chat => {
            chat.messages.push({ role, content, html, timestamp: Date.now() });
            if (role === "user" && (!chat.title || chat.title === "Nuevo chat")) {
                chat.title = content.slice(0, 48);
            }
        });
    }
    return node;
}

function loadChat(chatId) {
    activeChatId = chatId;
    setCookie(ACTIVE_CHAT_COOKIE, chatId);
    messages.innerHTML = "";
    const chat = getActiveChat();
    chat.messages.forEach(message => appendMessage(message.role, message.content, message.html, false));
    updateChatView();
}

function newChat() {
    activeChatId = createChatId();
    messages.innerHTML = "";
    updateActiveChat(chat => {
        chat.title = "Nuevo chat";
        chat.messages = [];
    });
    updateChatView();
}

function deleteChat(chatId) {
    const chats = getChats();
    const remaining = chats.filter(chat => chat.id !== chatId);

    if (!remaining.length) {
        activeChatId = createChatId();
        messages.innerHTML = "";
        updateActiveChat(chat => {
            chat.title = "Nuevo chat";
            chat.messages = [];
        });
        updateChatView();
        renderHistory();
        return;
    }

    saveChats(remaining);

    if (chatId === activeChatId) {
        activeChatId = remaining[0].id;
        setCookie(ACTIVE_CHAT_COOKIE, activeChatId);
        loadChat(activeChatId);
        return;
    }

    renderHistory();
}

function deletePreviousChats() {
    const chats = getChats();
    const remaining = chats.filter(chat => chat.id === activeChatId);
    saveChats(remaining);
    renderHistory();
}

function renderHistory(filter = "") {
    const history = document.getElementById("chatHistory");
    if (!history) return;
    const chats = getChats().filter(chat => chat.messages.length || chat.title !== "Nuevo chat");
    const filtered = chats.filter(chat => chat.title.toLowerCase().includes(filter.toLowerCase()));
    const previousCount = chats.filter(chat => chat.id !== activeChatId).length;

    history.innerHTML = `
        <div class="history-header">
            <p>Chats guardados</p>
            <button type="button" class="history-clear" id="clearPreviousChats" ${previousCount ? "" : "disabled"}>Eliminar anteriores</button>
        </div>
    `;

    document.getElementById("clearPreviousChats")?.addEventListener("click", () => {
        if (!previousCount) return;
        if (!window.confirm("¿Quieres eliminar los chats anteriores?")) return;
        deletePreviousChats();
    });

    if (!filtered.length) {
        const empty = document.createElement("span");
        empty.className = "empty-state";
        empty.textContent = "No hay chats guardados.";
        history.appendChild(empty);
        return;
    }

    filtered.forEach(chat => {
        const row = document.createElement("div");
        row.className = "history-row";

        const item = document.createElement("button");
        item.type = "button";
        item.className = `history-chat${chat.id === activeChatId ? " active" : ""}`;
        item.textContent = chat.title || "Chat sin titulo";
        item.addEventListener("click", () => loadChat(chat.id));

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "history-remove";
        remove.setAttribute("aria-label", "Eliminar chat");
        remove.textContent = "×";
        remove.addEventListener("click", event => {
            event.stopPropagation();
            if (!window.confirm("¿Eliminar este chat del historial?")) return;
            deleteChat(chat.id);
        });

        row.appendChild(item);
        row.appendChild(remove);
        history.appendChild(row);
    });
}

async function sendMessage(text, isVoice = false) {
    const cleanText = (text || "").trim();
    if (!cleanText) return;

    appendMessage("user", cleanText);
    const botMessage = appendMessage("assistant", "Pensando...", '<span class="spinner-border spinner-border-sm"></span> Pensando...', false);

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: buildOutgoingText(cleanText) }),
        });
        const data = await response.json();
        const html = normalizeBotResponse(data.response || data.error || "No se recibió respuesta.");
        const spokenText = plainTextFromHtml(html);

        botMessage.innerHTML = html;
        updateActiveChat(chat => {
            chat.messages.push({ role: "assistant", content: spokenText, html, timestamp: Date.now() });
        });

        if (isVoice || voiceMode?.checked) {
            const played = await playBackendAudio(data.audio_response || "");
            if (!played) {
                speak(spokenText);
            }
        }
    } catch (error) {
        const html = "Error en el servidor. Intenta nuevamente.";
        botMessage.textContent = html;
        updateActiveChat(chat => {
            chat.messages.push({ role: "assistant", content: html, html: null, timestamp: Date.now() });
        });
    }

    scrollChatToBottom();
}

function startChat() {
    const text = welcomeInput.value.trim();
    if (!text) return;
    welcomeInput.value = "";
    sendMessage(text);
}

function sendFromInput() {
    const text = chatInput.value.trim();
    if (!text) return;
    chatInput.value = "";
    sendMessage(text);
}

function getSpanishFemaleVoice() {
    const voices = window.speechSynthesis?.getVoices?.() || [];
    const preferred = [
        "Sabina", "Helena", "Lucia", "Mónica", "Monica", "Paulina", "Elvira", "Google español",
        "Microsoft Sabina", "Microsoft Helena", "Microsoft Laura"
    ];
    return voices.find(v => preferred.some(name => v.name.toLowerCase().includes(name.toLowerCase())))
        || voices.find(v => v.lang?.toLowerCase().startsWith("es") && /female|mujer|woman/i.test(v.name))
        || voices.find(v => v.lang?.toLowerCase().startsWith("es"))
        || voices[0];
}

function speak(text) {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "es-MX";
    utterance.rate = 0.96;
    utterance.pitch = 1.05;
    const voice = getSpanishFemaleVoice();
    if (voice) utterance.voice = voice;
    window.speechSynthesis.speak(utterance);
}

async function playBackendAudio(audioPath) {
    if (!audioPath) return false;

    try {
        const source = audioPath.startsWith("http") ? audioPath : `${window.location.origin}${audioPath}`;

        if (window.speechSynthesis) {
            window.speechSynthesis.cancel();
        }

        if (window.__vozSeguraAudio instanceof Audio) {
            window.__vozSeguraAudio.pause();
            window.__vozSeguraAudio.currentTime = 0;
        }

        const audio = new Audio(source);
        window.__vozSeguraAudio = audio;
        await audio.play();
        return true;
    } catch {
        return false;
    }
}

function setupSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return null;
    const instance = new SpeechRecognition();
    instance.lang = "es-MX";
    instance.interimResults = true;
    instance.continuous = false;
    return instance;
}

function startBrowserMic() {
    recognition = recognition || setupSpeechRecognition();
    if (!recognition) {
        audioStatus.textContent = "Tu navegador no soporta reconocimiento de voz. Prueba Chrome o Edge.";
        return;
    }

    let finalText = "";
    recognition.onresult = event => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) finalText += transcript;
            else interim += transcript;
        }
        audioStatus.textContent = finalText || interim || "Escuchando...";
    };
    recognition.onend = () => {
        startRecordingButton.disabled = false;
        stopRecordingButton.disabled = true;
        audioModal.hide();
        if (finalText.trim()) sendMessage(finalText.trim(), true);
    };
    recognition.onerror = event => {
        audioStatus.textContent = `Error de micrófono: ${event.error}`;
        startRecordingButton.disabled = false;
        stopRecordingButton.disabled = true;
    };
    audioStatus.textContent = "Escuchando...";
    startRecordingButton.disabled = true;
    stopRecordingButton.disabled = false;
    recognition.start();
}

function stopBrowserMic() {
    if (recognition) recognition.stop();
}

function openPanel(type) {
    if (!panel) return;
    const titles = {
        search: ["Buscar chats", "Busca en tu historial guardado en este navegador"],
        library: ["Biblioteca", "PDFs disponibles para la busqueda semantica"],
        format: ["Formato", "Acceso al formato oficial de denuncia"],
        denuncias: ["Denuncias", "Inicia o continua el flujo de denuncia"],
        tools: ["Herramientas", "Ajustes rápidos del chat"],
        upload: ["Cargar archivos", "Agrega PDFs a la biblioteca"],
        reason: ["Razonar", "Modo de respuesta mas cuidadoso"],
    };
    const [title, subtitle] = titles[type] || titles.tools;
    panelTitle.textContent = title;
    panelSubtitle.textContent = subtitle;
    panelBody.innerHTML = "";
    panel.classList.add("open");

    if (type === "search") renderSearchPanel();
    else if (type === "library") renderLibraryPanel();
    else if (type === "format") renderFormatPanel();
    else if (type === "denuncias") renderDenunciasPanel();
    else if (type === "upload") renderUploadPanel();
    else if (type === "reason") renderReasonPanel();
    else renderToolsPanel();
}

function closePanel() {
    panel?.classList.remove("open");
}

function renderSearchPanel() {
    panelBody.innerHTML = `
        <input class="panel-input" id="chatSearchInput" placeholder="Buscar por título o mensaje...">
        <button class="panel-primary" id="searchFromPanel">Buscar en documentos</button>
        <div class="panel-list" id="chatSearchResults"></div>
    `;
    const input = document.getElementById("chatSearchInput");
    const results = document.getElementById("chatSearchResults");
    document.getElementById("searchFromPanel").addEventListener("click", () => {
        const term = input.value.trim();
        if (!term) return;
        setComposeMode("search");
        closePanel();
        sendMessage(term);
    });
    const draw = () => {
        const term = input.value.toLowerCase();
        const chats = getChats().filter(chat =>
            chat.title.toLowerCase().includes(term)
            || chat.messages.some(m => (m.content || "").toLowerCase().includes(term))
        );
        results.innerHTML = chats.length ? "" : `<p class="empty-state">No se encontraron chats.</p>`;
        chats.forEach(chat => {
            const btn = document.createElement("button");
            btn.className = "panel-row";
            btn.innerHTML = `<strong>${chat.title}</strong><span>${new Date(chat.updatedAt).toLocaleString()}</span>`;
            btn.addEventListener("click", () => {
                loadChat(chat.id);
                closePanel();
            });
            results.appendChild(btn);
        });
    };
    input.addEventListener("input", draw);
    draw();
}

async function renderLibraryPanel() {
    panelBody.innerHTML = `
        <label class="upload-box">
            <input type="file" id="pdfUpload" accept="application/pdf" multiple hidden>
            <strong>Cargar PDFs</strong>
            <span>Selecciona documentos para agregarlos a la biblioteca.</span>
        </label>
        <div class="panel-list" id="libraryList"><p class="empty-state">Cargando...</p></div>
    `;
    document.getElementById("pdfUpload").addEventListener("change", uploadPdfs);
    await loadLibraryList();
}

async function loadLibraryList() {
    const list = document.getElementById("libraryList");
    if (!list) return;
    const response = await fetch("/api/library");
    const data = await response.json();
    list.innerHTML = data.files.length ? "" : `<p class="empty-state">No hay PDFs en la biblioteca.</p>`;
    data.files.forEach(file => {
        const row = document.createElement("a");
        row.className = "panel-row";
        row.href = file.url;
        row.target = "_blank";
        row.innerHTML = `<strong>${file.name}</strong><span>${formatBytes(file.size)}</span>`;
        list.appendChild(row);
    });
}

async function uploadPdfs(event) {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    const formData = new FormData();
    files.forEach(file => formData.append("files", file));
    const response = await fetch("/api/library/upload", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) {
        alert(data.error || "No se pudieron cargar los PDFs.");
        return;
    }
    await loadLibraryList();
    appendMessage("assistant", data.message, data.message);
}

function renderUploadPanel() {
    renderLibraryPanel();
}

function renderFormatPanel() {
    panelBody.innerHTML = `
        <a class="panel-primary" href="/download_form" target="_blank">Descargar formato oficial</a>
        <button class="panel-row" id="askFormatHelp"><strong>Ayudame a llenarlo</strong><span>Inicia el flujo guiado</span></button>
    `;
    document.getElementById("askFormatHelp").addEventListener("click", () => {
        closePanel();
        sendMessage("Quiero hacer una denuncia");
    });
}

function renderDenunciasPanel() {
    panelBody.innerHTML = `
        <button class="panel-primary" id="startDenuncia">Iniciar denuncia</button>
        <button class="panel-row" id="orientacionDenuncia"><strong>Recibir orientacion</strong><span>Conocer pasos y derechos antes de denunciar</span></button>
        <button class="panel-row" id="downloadGenerated"><strong>Descargar denuncia generada</strong><span>Disponible si ya fue creada</span></button>
    `;
    document.getElementById("startDenuncia").addEventListener("click", () => {
        closePanel();
        sendMessage("Quiero hacer una denuncia");
    });
    document.getElementById("orientacionDenuncia").addEventListener("click", () => {
        closePanel();
        sendMessage("¿Cómo puedo presentar una denuncia?");
    });
    document.getElementById("downloadGenerated").addEventListener("click", () => window.open("/download_sue", "_blank"));
}

function renderReasonPanel() {
    panelBody.innerHTML = `
        <button class="panel-primary" id="activateReason">Activar modo razonar</button>
        <button class="panel-row" id="reasonCurrent"><strong>Razonar mi pregunta actual</strong><span>Usa el texto escrito en la caja de mensaje</span></button>
        <p class="panel-note">Este modo responde con más cuidado, marca supuestos y recuerda verificar la información importante.</p>
    `;
    document.getElementById("activateReason").addEventListener("click", () => {
        setComposeMode("reason");
        closePanel();
        getCurrentDraft()?.focus();
    });
    document.getElementById("reasonCurrent").addEventListener("click", () => {
        const input = getCurrentDraft();
        const text = input?.value.trim();
        if (!text) return;
        input.value = "";
        setComposeMode("reason");
        closePanel();
        sendMessage(text);
    });
}

function renderToolsPanel() {
    panelBody.innerHTML = `
        <label class="panel-toggle"><input type="checkbox" id="panelVoiceToggle"> Respuestas por voz</label>
        <button class="panel-row" id="activateSearchMode"><strong>Modo buscar</strong><span>Enfoca la siguiente consulta en documentos e historial</span></button>
        <button class="panel-row" id="activateReasonMode"><strong>Modo razonar</strong><span>Respuestas más cuidadosas, con supuestos y verificación</span></button>
        <button class="panel-row" id="testVoice"><strong>Probar voz femenina</strong><span>Usa la mejor voz en español disponible en tu navegador</span></button>
        <button class="panel-row" id="newChatPanel"><strong>Nuevo chat</strong><span>Guarda el historial actual y empieza limpio</span></button>
        <button class="panel-row" id="deletePreviousPanel"><strong>Eliminar chats anteriores</strong><span>Borra todos menos el chat actual</span></button>
    `;
    const toggle = document.getElementById("panelVoiceToggle");
    toggle.checked = !!voiceMode?.checked;
    toggle.addEventListener("change", () => {
        if (voiceMode) voiceMode.checked = toggle.checked;
    });
    document.getElementById("testVoice").addEventListener("click", () => speak("Hola, soy Voz Segura. Esta es la voz seleccionada para tus respuestas."));
    document.getElementById("activateSearchMode").addEventListener("click", () => {
        setComposeMode("search");
        closePanel();
        getCurrentDraft()?.focus();
    });
    document.getElementById("activateReasonMode").addEventListener("click", () => {
        setComposeMode("reason");
        closePanel();
        getCurrentDraft()?.focus();
    });
    document.getElementById("newChatPanel").addEventListener("click", () => {
        newChat();
        closePanel();
    });
    document.getElementById("deletePreviousPanel").addEventListener("click", () => {
        if (!window.confirm("¿Quieres eliminar los chats anteriores?")) return;
        deletePreviousChats();
        closePanel();
    });
}

function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function proxyWheelToMessages(event) {
    if (!document.body.classList.contains("has-messages") || !chatContainer) return;
    if (chatContainer.scrollHeight <= chatContainer.clientHeight) return;

    // Mantener el comportamiento nativo dentro de paneles/modales o del propio contenedor.
    if (event.target.closest(".app-panel, .modal, #chatContainer, #messages, .message-container, .chat-body")) return;

    event.preventDefault();
    chatContainer.scrollTop += event.deltaY;
}

document.addEventListener("DOMContentLoaded", () => {
    getActiveChat();
    loadChat(activeChatId);
    renderHistory();
    updateModeButtons();

    const mainArea = document.querySelector(".cg-main");
    chatContainer?.addEventListener("wheel", proxyWheelToMessages, { passive: false });
    mainArea?.addEventListener("wheel", proxyWheelToMessages, { passive: false });
    document.getElementById("sidebarNewChat")?.addEventListener("click", () => {
        newChat();
    });

    if (window.speechSynthesis) {
        window.speechSynthesis.onvoiceschanged = getSpanishFemaleVoice;
    }
});

welcomeSendButton?.addEventListener("click", startChat);
welcomeInput?.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        startChat();
    }
});

sendButton?.addEventListener("click", sendFromInput);
chatInput?.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendFromInput();
    }
});

document.getElementById("confirmDelete")?.addEventListener("click", async () => {
    await fetch("/confirm_clear", { method: "POST", headers: { "Content-Type": "application/json" } });
    newChat();
    bootstrap.Modal.getInstance(document.getElementById("confirmModal"))?.hide();
});

document.querySelectorAll("[data-panel]").forEach(element => {
    element.addEventListener("click", event => {
        event.preventDefault();
        openPanel(element.dataset.panel);
    });
});

document.querySelectorAll("[data-tool]").forEach(element => {
    element.addEventListener("click", event => {
        event.preventDefault();
        const tool = element.dataset.tool;
        if (tool === "search" || tool === "reason") {
            const input = getCurrentDraft();
            const text = input?.value.trim();
            setComposeMode(tool);
            if (text) {
                input.value = "";
                sendMessage(text);
            } else {
                openPanel(tool);
            }
            return;
        }
        openPanel(tool);
    });
});

document.querySelectorAll("[data-prompt]").forEach(element => {
    element.addEventListener("click", () => {
        const prompt = element.dataset.prompt;
        if (welcomeMessage?.style.display !== "none") {
            welcomeInput.value = prompt;
            welcomeInput.focus();
        } else {
            chatInput.value = prompt;
            chatInput.focus();
        }
    });
});

panelClose?.addEventListener("click", closePanel);

const audioModalEl = document.getElementById("audioModal");
const audioModal = audioModalEl ? new bootstrap.Modal(audioModalEl) : null;
const audioStatus = document.getElementById("audioStatus");
const startRecordingButton = document.getElementById("startRecording");
const stopRecordingButton = document.getElementById("stopRecording");

document.getElementById("Audio")?.addEventListener("click", () => {
    audioStatus.textContent = 'Presiona "Grabar" para iniciar la grabación.';
    startRecordingButton.disabled = false;
    stopRecordingButton.disabled = true;
    audioModal?.show();
});

startRecordingButton?.addEventListener("click", startBrowserMic);
stopRecordingButton?.addEventListener("click", stopBrowserMic);

if (window.innerWidth <= 768 && window.location.pathname !== "/movile") {
    window.location.href = "/movile";
} else if (window.innerWidth > 768 && window.location.pathname !== "/") {
    window.location.href = "/";
}
