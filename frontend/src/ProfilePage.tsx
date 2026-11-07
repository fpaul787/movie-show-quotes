import { useEffect, useState, type FormEvent } from "react";

type Profile = {
  username: string;
  email: string | null;
};

type UserApiKey = {
  name: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
  key?: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseApiKey(data: unknown): UserApiKey | null {
  if (!isRecord(data) || !("api_key" in data)) {
    throw new Error("Could not load your API key. Please try again.");
  }
  if (data.api_key === null) return null;

  const key = data.api_key;
  if (
    !isRecord(key) ||
    typeof key.name !== "string" ||
    typeof key.is_active !== "boolean" ||
    typeof key.created_at !== "string" ||
    !(key.last_used_at === null || typeof key.last_used_at === "string") ||
    ("key" in key && typeof key.key !== "string")
  ) {
    throw new Error("Could not load your API key. Please try again.");
  }

  return {
    name: key.name,
    is_active: key.is_active,
    created_at: key.created_at,
    last_used_at: key.last_used_at,
    ...(typeof key.key === "string" ? { key: key.key } : {}),
  };
}

function ProfilePage() {
  const isApiKeysPage =
    window.location.pathname.replace(/\/+$/, "") === "/profile/api-keys";
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [emailInput, setEmailInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [apiKey, setApiKey] = useState<UserApiKey | null>(null);
  const [apiKeyLoading, setApiKeyLoading] = useState(true);
  const [apiKeyCreating, setApiKeyCreating] = useState(false);
  const [apiKeyDeleting, setApiKeyDeleting] = useState(false);
  const [confirmApiKeyDelete, setConfirmApiKeyDelete] = useState(false);
  const [apiKeyError, setApiKeyError] = useState("");
  const [newApiKeySecret, setNewApiKeySecret] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState("");

  function startEditing() {
    setEmailInput(profile?.email ?? "");
    setSaveError("");
    setEditing(true);
  }

  async function saveEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setSaveError("");

    try {
      const csrfResponse = await fetch("/api/auth/csrf", {
        credentials: "same-origin",
      });
      const csrfData: unknown = await csrfResponse.json();
      if (
        !csrfResponse.ok ||
        typeof csrfData !== "object" ||
        csrfData === null ||
        typeof (csrfData as { csrfToken?: unknown }).csrfToken !== "string"
      ) {
        throw new Error("Could not save. Please try again.");
      }

      const response = await fetch("/api/auth/profile", {
        method: "PATCH",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": (csrfData as { csrfToken: string }).csrfToken,
        },
        body: JSON.stringify({ email: emailInput.trim() }),
      });
      const data = await response.json().catch(() => null);

      if (response.status === 401) {
        window.location.replace("/login/");
        return;
      }
      if (!response.ok) {
        const message = data?.errors?.email?.[0]?.message;
        throw new Error(
          typeof message === "string" ? message : "Could not save. Please try again.",
        );
      }

      setProfile(data as Profile);
      setEditing(false);
    } catch (requestError) {
      setSaveError(
        requestError instanceof Error
          ? requestError.message
          : "Could not save. Please try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    if (isApiKeysPage) {
      async function loadApiKey() {
        try {
          const response = await fetch("/api/keys", {
            credentials: "same-origin",
          });
          if (response.status === 401) {
            window.location.replace("/login/");
            return;
          }
          if (!response.ok) {
            throw new Error("Could not load your API key. Please try again.");
          }
          setApiKey(parseApiKey(await response.json()));
        } catch (requestError) {
          setApiKeyError(
            requestError instanceof Error
              ? requestError.message
              : "Could not load your API key. Please try again.",
          );
        } finally {
          setApiKeyLoading(false);
        }
      }

      void loadApiKey();
      return;
    }

    async function load() {
      try {
        const response = await fetch("/api/auth/profile", {
          credentials: "same-origin",
        });
        if (response.status === 401) {
          window.location.replace("/login/");
          return;
        }
        if (!response.ok) throw new Error();
        const data = (await response.json()) as Profile;
        setProfile(data);
      } catch {
        setError("Could not load your profile. Please try again.");
      }
    }
    void load();
  }, [isApiKeysPage]);

  async function createApiKey() {
    setApiKeyCreating(true);
    setApiKeyError("");
    setCopyMessage("");

    try {
      const csrfResponse = await fetch("/api/auth/csrf", {
        credentials: "same-origin",
      });
      if (!csrfResponse.ok) {
        throw new Error("Could not start API key creation. Please try again.");
      }
      const csrfData: unknown = await csrfResponse.json();
      if (!isRecord(csrfData) || typeof csrfData.csrfToken !== "string") {
        throw new Error("Could not start API key creation. Please try again.");
      }

      const response = await fetch("/api/keys", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfData.csrfToken },
      });
      if (response.status === 401) {
        window.location.replace("/login/");
        return;
      }
      if (response.status === 409) {
        throw new Error("An API key already exists for your account.");
      }
      if (!response.ok) {
        throw new Error("Could not create your API key. Please try again.");
      }

      const createdKey = parseApiKey(await response.json());
      if (!createdKey?.key) {
        throw new Error("Could not create your API key. Please try again.");
      }
      setApiKey(createdKey);
      setNewApiKeySecret(createdKey.key);
    } catch (requestError) {
      setApiKeyError(
        requestError instanceof Error
          ? requestError.message
          : "Could not create your API key. Please try again.",
      );
    } finally {
      setApiKeyCreating(false);
    }
  }

  async function copyApiKey() {
    if (!newApiKeySecret) return;
    try {
      await navigator.clipboard.writeText(newApiKeySecret);
      setCopyMessage("Copied to clipboard.");
    } catch {
      setApiKeyError("Could not copy the API key. Please allow clipboard access and try again.");
    }
  }

  async function deleteApiKey() {
    setApiKeyDeleting(true);
    setApiKeyError("");

    try {
      const csrfResponse = await fetch("/api/auth/csrf", {
        credentials: "same-origin",
      });
      if (!csrfResponse.ok) {
        throw new Error("Could not start API key deletion. Please try again.");
      }
      const csrfData: unknown = await csrfResponse.json();
      if (!isRecord(csrfData) || typeof csrfData.csrfToken !== "string") {
        throw new Error("Could not start API key deletion. Please try again.");
      }

      const response = await fetch("/api/keys", {
        method: "DELETE",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfData.csrfToken },
      });
      if (response.status === 401) {
        window.location.replace("/login/");
        return;
      }
      if (response.status === 404) {
        setApiKey(null);
        setNewApiKeySecret(null);
        setConfirmApiKeyDelete(false);
        return;
      }
      if (!response.ok) {
        throw new Error("Could not delete your API key. Please try again.");
      }

      setApiKey(null);
      setNewApiKeySecret(null);
      setConfirmApiKeyDelete(false);
      setCopyMessage("");
    } catch (requestError) {
      setApiKeyError(
        requestError instanceof Error
          ? requestError.message
          : "Could not delete your API key. Please try again.",
      );
    } finally {
      setApiKeyDeleting(false);
    }
  }

  return (
    <div className="site-shell">
      <header className="site-header">
        <a className="brand" href="/" aria-label="Movie and Show Quotes homepage">
          <span className="brand-mark" aria-hidden="true">“</span>
          <span>Movie <span className="brand-amp">&amp;</span> Show Quotes</span>
        </a>
      </header>

      <main className="profile-main">
        <div className="profile-layout">
          <nav className="profile-sidebar" aria-label="Account navigation">
            <a
              className={`profile-nav-link${isApiKeysPage ? "" : " is-active"}`}
              href="/profile/"
              aria-current={isApiKeysPage ? undefined : "page"}
            >
              Profile
            </a>
            <a
              className={`profile-nav-link${isApiKeysPage ? " is-active" : ""}`}
              href="/profile/api-keys/"
              aria-current={isApiKeysPage ? "page" : undefined}
            >
              API Keys
            </a>
          </nav>

          {isApiKeysPage ? (
            <section className="signup-card profile-card" aria-labelledby="api-keys-title">
              <div className="eyebrow"><span className="eyebrow-dot" /> Developer access</div>
              <h1 id="api-keys-title" className="signup-title">API Keys.</h1>
              <p className="signup-description">
                Use your key to authenticate requests to the quotes API.
              </p>

              {apiKeyError && <p className="signup-error" role="alert">{apiKeyError}</p>}
              {apiKeyLoading && <p className="signup-description">Loading your API key…</p>}
              {!apiKeyLoading && !apiKeyError && !apiKey && (
                <>
                  <p className="signup-description">You don’t have an API key yet.</p>
                  <button
                    className="signup-submit"
                    type="button"
                    onClick={createApiKey}
                    disabled={apiKeyCreating}
                  >
                    {apiKeyCreating ? "Creating…" : "Create API key"}
                  </button>
                </>
              )}
              {apiKey && (
                <div className="api-key-details">
                  <dl className="profile-details">
                    <dt>Name</dt>
                    <dd>{apiKey.name}</dd>
                    <dt>Status</dt>
                    <dd>{apiKey.is_active ? "Active" : "Inactive"}</dd>
                    <dt>Created</dt>
                    <dd>{new Date(apiKey.created_at).toLocaleString()}</dd>
                    <dt>Last used</dt>
                    <dd>{apiKey.last_used_at ? new Date(apiKey.last_used_at).toLocaleString() : "Never"}</dd>
                  </dl>
                  {newApiKeySecret ? (
                    <div className="api-key-secret">
                      <p className="signup-description">
                        Your key is hidden. Copy it now; it won’t be available again after you leave this page.
                      </p>
                      <code aria-label="Hidden API key" aria-live="polite">••••••••••••••••</code>
                      <button className="signup-submit" type="button" onClick={copyApiKey}>
                        Copy key
                      </button>
                      {copyMessage && <p className="api-key-copy-message" role="status">{copyMessage}</p>}
                    </div>
                  ) : (
                    <p className="signup-description">
                      The full key is only shown when it’s first created.
                    </p>
                  )}
                  {confirmApiKeyDelete ? (
                    <div className="api-key-delete-confirmation" role="group" aria-label="Confirm API key deletion">
                      <p className="signup-description">
                        Deleting this key immediately revokes it. You’ll be able to create a new key afterward.
                      </p>
                      <div className="api-key-delete-actions">
                        <button
                          className="api-key-delete-button"
                          type="button"
                          onClick={deleteApiKey}
                          disabled={apiKeyDeleting}
                        >
                          {apiKeyDeleting ? "Deleting…" : "Confirm delete"}
                        </button>
                        <button
                          className="api-key-cancel-button"
                          type="button"
                          onClick={() => setConfirmApiKeyDelete(false)}
                          disabled={apiKeyDeleting}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      className="api-key-delete-button"
                      type="button"
                      onClick={() => {
                        setApiKeyError("");
                        setConfirmApiKeyDelete(true);
                      }}
                    >
                      Delete API key
                    </button>
                  )}
                </div>
              )}
            </section>
          ) : (
            <section className="signup-card profile-card" aria-labelledby="profile-title">
              <div className="eyebrow"><span className="eyebrow-dot" /> Your account</div>
              <h1 id="profile-title" className="signup-title">Profile.</h1>

              {error && <p className="signup-error" role="alert">{error}</p>}
              {profile && !editing && (
                <>
                  <dl className="profile-details">
                    <dt>Username</dt>
                    <dd>{profile.username}</dd>
                    <dt>Email</dt>
                    <dd>{profile.email ?? "Not provided"}</dd>
                  </dl>
                  <button className="signup-submit" type="button" onClick={startEditing}>
                    Change email
                  </button>
                </>
              )}
              {profile && editing && (
                <form className="signup-form" onSubmit={saveEmail}>
                  <label className="signup-field">
                    <span>Email (leave blank to remove)</span>
                    <input
                      type="email"
                      name="email"
                      autoComplete="email"
                      maxLength={254}
                      value={emailInput}
                      onChange={(event) => setEmailInput(event.target.value)}
                    />
                  </label>
                  {saveError && <p className="signup-error" role="alert">{saveError}</p>}
                  <button className="signup-submit" type="submit" disabled={saving}>
                    {saving ? "Saving…" : "Save"}
                  </button>
                  <button
                    className="signup-submit"
                    type="button"
                    onClick={() => setEditing(false)}
                    disabled={saving}
                  >
                    Cancel
                  </button>
                </form>
              )}
            </section>
          )}
        </div>
      </main>

      <footer className="site-footer">
        <a className="footer-brand" href="/">Movie <span>&amp;</span> Show Quotes</a>
        <span>For the love of a good story.</span>
      </footer>
    </div>
  );
}

export default ProfilePage;
