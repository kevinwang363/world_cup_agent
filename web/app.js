const messagesEl = document.querySelector("#messages");
const formEl = document.querySelector("#chatForm");
const inputEl = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const resetButton = document.querySelector("#resetButton");
const sessionLabel = document.querySelector("#sessionLabel");
const quickQuestions = document.querySelectorAll(".quick-question");

let sessionId = localStorage.getItem("worldCupAgentSessionId") || crypto.randomUUID();
localStorage.setItem("worldCupAgentSessionId", sessionId);
sessionLabel.textContent = `会话 ${sessionId.slice(0, 8)}`;

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderMarkdownLite(text) {
  const lines = escapeHtml(text).split("\n");
  let html = "";
  let inList = false;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      continue;
    }

    if (trimmed.startsWith("### ")) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      html += `<p><strong>${trimmed.slice(4)}</strong></p>`;
      continue;
    }

    if (trimmed.startsWith("## ")) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      html += `<p><strong>${trimmed.slice(3)}</strong></p>`;
      continue;
    }

    if (trimmed.startsWith("- ")) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += `<li>${trimmed.slice(2)}</li>`;
      continue;
    }

    if (inList) {
      html += "</ul>";
      inList = false;
    }
    html += `<p>${trimmed}</p>`;
  }

  if (inList) {
    html += "</ul>";
  }

  return html.replaceAll(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
}

function renderMarkdown(text) {
  if (window.marked) {
    marked.setOptions({
      breaks: true,
      gfm: true,
    });
    return marked.parse(text);
  }

  return renderMarkdownLite(text);
}

function appendMessage(role, content, options = {}) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  if (options.id) {
    article.id = options.id;
  }

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "你" : "⚽";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (options.typing) {
    bubble.classList.add("typing");
    bubble.innerHTML = "<strong>World Cup Agent</strong><p>正在看比赛数据和知识库...</p>";
  } else {
    const name = role === "user" ? "你" : "World Cup Agent";
    bubble.innerHTML = `<strong>${name}</strong>${role === "user" ? renderMarkdownLite(content) : renderMarkdown(content)}`;
  }

  article.append(avatar, bubble);
  messagesEl.append(article);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return article;
}

async function sendMessage(message) {
  appendMessage("user", message);
  inputEl.value = "";
  sendButton.disabled = true;
  inputEl.disabled = true;
  const agentMessage = createStreamingMessage();
  let answer = "";
  let buffer = "";

  try {
    const response = await fetch("/api/chat-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });

    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "请求失败");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) {
          continue;
        }
        const event = JSON.parse(line);
        answer = handleStreamEvent(event, agentMessage, answer);
      }
    }

    if (buffer.trim()) {
      const event = JSON.parse(buffer);
      handleStreamEvent(event, agentMessage, answer);
    }
  } catch (error) {
    agentMessage.status.textContent = "这次进攻中断";
    agentMessage.content.innerHTML = renderMarkdown(`服务暂时没有完成这次进攻：${error.message}`);
  } finally {
    sendButton.disabled = false;
    inputEl.disabled = false;
    inputEl.focus();
  }
}

function createStreamingMessage() {
  const article = document.createElement("article");
  article.className = "message agent streaming";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "⚽";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const title = document.createElement("strong");
  title.textContent = "World Cup Agent";

  const process = document.createElement("div");
  process.className = "process-log";

  const status = document.createElement("div");
  status.className = "process-item active";
  status.textContent = "等待开球...";

  const content = document.createElement("div");
  content.className = "answer-content";

  process.append(status);
  bubble.append(title, process, content);
  article.append(avatar, bubble);
  messagesEl.append(article);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  return { article, process, status, content };
}

function addProcessItem(agentMessage, text, className = "") {
  const item = document.createElement("div");
  item.className = `process-item ${className}`.trim();
  item.textContent = text;
  agentMessage.process.append(item);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return item;
}

function handleStreamEvent(event, agentMessage, answer) {
  if (event.event === "session") {
    sessionId = event.session_id;
    localStorage.setItem("worldCupAgentSessionId", sessionId);
    sessionLabel.textContent = `会话 ${sessionId.slice(0, 8)}`;
    return answer;
  }

  if (event.event === "status") {
    agentMessage.status.textContent = event.message;
    return answer;
  }

  if (event.event === "tool_start") {
    agentMessage.status.textContent = event.label;
    addProcessItem(agentMessage, `⚙ ${event.label}`, "active");
    return answer;
  }

  if (event.event === "tool_end") {
    addProcessItem(agentMessage, "✓ 工具返回结果，继续组织回答", "done");
    return answer;
  }

  if (event.event === "tool_error") {
    addProcessItem(agentMessage, `! 工具调用失败：${event.message}`, "error");
    return answer;
  }

  if (event.event === "token") {
    const nextAnswer = answer + event.text;
    agentMessage.content.innerHTML = renderMarkdown(nextAnswer);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return nextAnswer;
  }

  if (event.event === "done") {
    const finalAnswer = event.answer || answer;
    agentMessage.status.textContent = "终场哨，回答完成";
    agentMessage.content.innerHTML = renderMarkdown(finalAnswer);
    sessionId = event.session_id || sessionId;
    localStorage.setItem("worldCupAgentSessionId", sessionId);
    sessionLabel.textContent = `会话 ${sessionId.slice(0, 8)}`;
    return finalAnswer;
  }

  if (event.event === "error") {
    agentMessage.status.textContent = "这次进攻中断";
    agentMessage.content.innerHTML = renderMarkdown(event.message || "请求失败");
    return answer;
  }

  return answer;
}

formEl.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = inputEl.value.trim();
  if (message) {
    sendMessage(message);
  }
});

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    formEl.requestSubmit();
  }
});

quickQuestions.forEach((button) => {
  button.addEventListener("click", () => {
    inputEl.value = button.textContent;
    formEl.requestSubmit();
  });
});

resetButton.addEventListener("click", async () => {
  await fetch("/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });

  sessionId = crypto.randomUUID();
  localStorage.setItem("worldCupAgentSessionId", sessionId);
  sessionLabel.textContent = `会话 ${sessionId.slice(0, 8)}`;
  messagesEl.innerHTML = "";
  appendMessage("agent", "会话已重置。我们重新开球吧。");
});
