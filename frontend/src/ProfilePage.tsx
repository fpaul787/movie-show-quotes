import { useEffect, useState, type FormEvent } from "react";

type Profile = {
  username: string;
  email: string | null;
};

function ProfilePage() {
  const isApiKeysPage =
    window.location.pathname.replace(/\/+$/, "") === "/profile/api-keys";
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [emailInput, setEmailInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

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
    if (isApiKeysPage) return;

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

          {!isApiKeysPage && (
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
