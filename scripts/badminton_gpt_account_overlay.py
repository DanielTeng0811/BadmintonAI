"""Small, reviewable local-account adaptations applied to the pinned upstream build copy."""
from pathlib import Path


def replace_once(path, before, after):
    text = path.read_text()
    if text.count(before) != 1:
        raise RuntimeError(f"Pinned account overlay no longer matches {path}: {before[:65]}")
    path.write_text(text.replace(before, after, 1))


def apply(build):
    root = Path(build) / "vendor/nanobot"
    bootstrap = root / "webui/src/lib/bootstrap.ts"
    replace_once(bootstrap, '  window.location.assign(ACCESS_LOGOUT_PATH);', '''  void fetch("/auth/logout", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  }).then((response) => {
    if (!response.ok) throw new Error("Sign out failed");
    for (const key of Object.keys(window.localStorage)) {
      if (key.startsWith("nanobot")) window.localStorage.removeItem(key);
    }
    window.sessionStorage.clear();
    new BroadcastChannel("badminton-auth").postMessage("changed");
    window.location.replace("/auth/login");
  }).catch(() => window.location.assign("/auth/account"));''')
    # Reload pages restored from browser history instead of showing a prior user's DOM.
    entry = root / "webui/src/main.tsx"
    entry.write_text(entry.read_text() + '''
window.addEventListener("pageshow", (event) => {
  if (event.persisted) window.location.reload();
});
const localAccountChannel = new BroadcastChannel("badminton-auth");
localAccountChannel.onmessage = () => window.location.reload();
''')
    client = root / "webui/src/lib/nanobot-client.ts"
    replace_once(client, "  private handleClose(event?: { code?: number }): void {\n", '''  private handleClose(event?: { code?: number }): void {
    if (event?.code === 1008) {
      this.intentionallyClosed = true;
      window.location.replace("/auth/login");
    }
''')
    app = root / "webui/src/App.tsx"
    replace_once(app, "  const sidebarProps = {\n", "  const sidebarProps = {\n    accountEmail: account?.email,\n    onLogout,\n")
    sidebar = root / "webui/src/components/Sidebar.tsx"
    replace_once(sidebar, "interface SidebarProps {\n", "interface SidebarProps {\n  accountEmail?: string;\n  onLogout?: () => void;\n")
    replace_once(sidebar, "        <ConnectionBadge />", '''        {props.accountEmail && !collapsed ? (
          <div className="flex flex-col gap-1 px-2 pb-2">
            <Button asChild variant="ghost" className="min-h-11 justify-start">
              <a href="/auth/account" aria-label="本機帳號設定">{props.accountEmail.split("@")[0]}</a>
            </Button>
            <Button type="button" variant="ghost" onClick={props.onLogout} className="min-h-11 justify-start">
              {t("app.account.logout")}
            </Button>
          </div>
        ) : null}
        <ConnectionBadge />''')

    channel = root / "nanobot/channels/websocket.py"
    replace_once(channel, "import hmac\n", "import hmac\nimport hashlib\nfrom functools import wraps\n")
    replace_once(channel, "class WebSocketChannel(BaseChannel):", '''def _bind_outbound_account(method):
    @wraps(method)
    async def wrapped(self, msg):
        email = accounts.ledger().owner(f"websocket:{msg.chat_id}") if accounts.accounts_enabled() else None
        token = accounts.bind_webui_account(accounts.account_for_email(email) if email else None)
        try:
            return await method(self, msg)
        finally:
            accounts.reset_webui_account(token)
    return wrapped


class WebSocketChannel(BaseChannel):''')
    replace_once(channel, "    async def send(self, msg: OutboundMessage) -> None:\n", "    @_bind_outbound_account\n    async def send(self, msg: OutboundMessage) -> None:\n")
    replace_once(channel, "    def _sign_media_path(self, abs_path: Path) -> str | None:\n", '''    def _account_media_secret(self) -> bytes:
        if not accounts.accounts_enabled():
            return self._media_secret
        account = accounts.current_webui_account()
        email = account.email if account else accounts.current_account_email()
        # Capability URLs are scoped to the authenticated account, including admin.
        identity = email or "unattributed"
        return hmac.new(self._media_secret, identity.encode("utf-8"), hashlib.sha256).digest()

    def _sign_media_path(self, abs_path: Path) -> str | None:
''')
    text = channel.read_text()
    if text.count("secret=self._media_secret,") != 3:
        raise RuntimeError("Media signature overlay no longer matches pinned source")
    channel.write_text(text.replace("secret=self._media_secret,", "secret=self._account_media_secret(),"))
    # Large tool outputs can include conversation content; do not expose the shared cache.
    account = root / "nanobot/accounts.py"
    replace_once(account, '_UNREADABLE = ("sessions", "memory/history.jsonl", "memory/.cursor", "memory/.dream_cursor")',
                 '_UNREADABLE = ("sessions", "tool-results", "memory/history.jsonl", "memory/.cursor", "memory/.dream_cursor")')
