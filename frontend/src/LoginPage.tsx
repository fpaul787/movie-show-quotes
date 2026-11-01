import { useState, type FormEvent } from "react";

type LoginPayload = {
  username: string;
  password: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function getErrorMessage(data: unknown): string {
  if (isRecord(data) && typeof data.error === "string") {
    return data.error;
  }
  return "Could not log in. Please try again.";
}

function LoginPage() {
  const [form, setForm] = useState<LoginPayload>({ username: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function updateField(field: keyof LoginPayload, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const csrfResponse = await fetch("/api/auth/csrf", {
        credentials: "same-origin",
      });
      if (!csrfResponse.ok) {
        throw new Error("Could not start login. Please try again.");
      }

      const csrfData = await readJson(csrfResponse);
      if (!isRecord(csrfData) || typeof csrfData.csrfToken !== "string") {
        throw new Error("Could not start login. Please try again.");
      }

      const response = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfData.csrfToken,
        },
        body: JSON.stringify(form),
      });
      const data = await readJson(response);

      if (!response.ok) {
        throw new Error(getErrorMessage(data));
      }

      window.location.assign("/");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not log in. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="site-shell">
      <header className="site-header">
        <a className="brand" href="/" aria-label="Movie and Show Quotes homepage">
          <span className="brand-mark" aria-hidden="true">“</span>
          <span>Movie <span className="brand-amp">&amp;</span> Show Quotes</span>
        </a>
        <nav aria-label="Main navigation">
          <a href="/">Home</a>
        </nav>
      </header>

      <main className="signup-main">
        <section className="signup-card" aria-labelledby="login-title">
          <div className="eyebrow"><span className="eyebrow-dot" /> Welcome back</div>
          <h1 id="login-title" className="signup-title">Log in.</h1>
          <p className="signup-description">
            Sign in to your Movie &amp; Show Quotes account.
          </p>

          <form className="signup-form" onSubmit={submitLogin}>
            <label className="signup-field">
              <span>Username</span>
              <input
                type="text"
                name="username"
                autoComplete="username"
                required
                maxLength={150}
                value={form.username}
                onChange={(event) => updateField("username", event.target.value)}
              />
            </label>
            <label className="signup-field">
              <span>Password</span>
              <input
                type="password"
                name="password"
                autoComplete="current-password"
                required
                value={form.password}
                onChange={(event) => updateField("password", event.target.value)}
              />
            </label>

            {error && <p className="signup-error" role="alert">{error}</p>}

            <button className="signup-submit" type="submit" disabled={loading}>
              {loading ? "Logging in…" : "Log in"}
            </button>
          </form>

          <p className="signup-description">
            Don’t have an account? <a href="/signup/">Sign up</a>
          </p>
        </section>
      </main>

      <footer className="site-footer">
        <a className="footer-brand" href="/">Movie <span>&amp;</span> Show Quotes</a>
        <span>For the love of a good story.</span>
      </footer>
    </div>
  );
}

export default LoginPage;
