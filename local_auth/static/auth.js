"use strict";
const el = (id) => document.getElementById(id);
const clearChatCache = () => {
  for (const key of Object.keys(localStorage)) if (key.startsWith("nanobot")) localStorage.removeItem(key);
  sessionStorage.clear();
  new BroadcastChannel("badminton-auth").postMessage("changed");
};
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {cache:"no-store"} : {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "操作失敗，請稍後再試。");
  return value;
}
async function render() {
  const state = await api("/auth/me");
  const accountPage = location.pathname === "/auth/account";
  if (accountPage && state.user) {
    document.title = "帳號 · BadmintonGPT";
    el("heading").textContent = "你的帳號";
    el("description").textContent = "管理登入狀態與密碼。";
    el("kicker").textContent = "YOUR ACCOUNT";
    el("account").hidden = false;
    el("account-name").textContent = state.user.username;
    el("role").textContent = state.user.role === "admin" ? "管理員" : "一般使用者";
    el("logout").onclick = async () => {await api("/auth/logout", {}); clearChatCache(); location.replace("/auth/login");};
    el("change-password").onsubmit = async (event) => {
      event.preventDefault();
      try {
        if (el("new-password").value !== el("new-confirm").value) throw new Error("兩次密碼不一致。");
        await api("/auth/password", {current:el("current").value, password:el("new-password").value});
        clearChatCache(); location.replace("/auth/login");
      } catch (error) {el("password-error").textContent = error.message;}
    };
    if (state.user.role === "admin") {
      el("admin").hidden = false;
      const refreshUsers = async () => {
        const data = await api("/auth/users"); el("users").replaceChildren();
        for (const user of data.users) {
          const row = document.createElement("div"); row.className = "user-row";
          const label = document.createElement("span"); label.textContent = user.username + (user.disabled ? " · 已停用" : ""); row.append(label);
          if (user.role !== "admin") {
            const button = document.createElement("button"); button.textContent = user.disabled ? "啟用" : "停用";
            button.onclick = async () => {button.disabled=true; try {await api("/auth/users", {username:user.username, disabled:!user.disabled}); await refreshUsers();} catch(error) {el("password-error").textContent=error.message; button.disabled=false;}};
            row.append(button);
          }
          el("users").append(row);
        }
      };
      await refreshUsers();
    }
    return;
  }
  const setup = state.setup_required;
  const register = !setup && location.pathname === "/auth/register";
  el("credentials").hidden = false;
  if (setup || register) {
    el("heading").textContent = setup ? "建立管理員帳號" : "建立你的帳號";
    el("kicker").textContent = setup ? "FIRST SERVE" : "JOIN THE COURT";
    el("description").textContent = setup ? "設定 admin 的密碼，開始使用 BadmintonGPT。" : "不需要電子郵件驗證；帳號建立後即可登入。";
    el("submit").textContent = setup ? "建立管理員並開始" : "建立帳號";
    el("password").autocomplete = "new-password";
    el("confirmation").hidden = false;
    el("confirm").required = true;
  }
  if (setup) {el("username").value="admin"; el("username").readOnly=true;}
  else {
    const link = document.createElement("a"); link.href=register ? "/auth/login" : "/auth/register";
    link.textContent=register ? "已有帳號？登入" : "還沒有帳號？建立帳號";
    el("switch").append(link);
  }
  el("credentials").onsubmit = async (event) => {
    event.preventDefault(); el("error").textContent=""; el("submit").disabled=true;
    try {
      if ((setup || register) && el("password").value !== el("confirm").value) throw new Error("兩次密碼不一致。");
      await api(setup ? "/auth/setup" : register ? "/auth/register" : "/auth/login", {username:el("username").value, password:el("password").value});
      clearChatCache(); location.replace("/");
    } catch (error) {el("error").textContent=error.message; el("submit").disabled=false;}
  };
}
window.addEventListener("pageshow", (event) => {if (event.persisted) location.reload();});
render().catch((error) => {el("description").textContent=error.message;});
