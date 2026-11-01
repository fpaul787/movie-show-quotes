import { useState, type FormEvent } from "react";

type SignupPayload = {
  username: string;
  email: string;
  password1: string;
  password2: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getErrorMessage(data: unknown): string {
  if (!isRecord(data)) {
    return "Could not create your account. Please try again.";
  }

  if (typeof data.error === "string") {
    return data.error;
  }

  if (isRecord(data.errors)) {
    const messages = Object.entries(data.errors).flatMap(([field, errors]) => {
      if (!Array.isArray(errors)) return [];

      return errors.flatMap((error) => {
        if (!isRecord(error) || typeof error.message !== "string") return [];
        return [`${field}: ${error.message}`];
      });
    });

    if (messages.length > 0) return messages.join(" ");
  }

  return "Could not create your account. Please try again.";
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function SignupPage() {
  const [form, setForm] = useState<SignupPayload>({
    username: "",
    email: "",
    password1: "",
    password2: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function updateField(field: keyof SignupPayload, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submitSignup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const csrfResponse = await fetch("/api/auth/csrf", {
        credentials: "same-origin",
      });
      if (!csrfResponse.ok) {
        throw new Error("Could not start signup. Please try again.");
      }

      const csrfData = await readJson(csrfResponse);
      if (!isRecord(csrfData) || typeof csrfData.csrfToken !== "string") {
        throw new Error("Could not start signup. Please try again.");
      }

      const response = await fetch("/api/auth/signup", {
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
          : "Could not create your account. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="site-shell">
      <header className="site-header">
        <a
          className="brand"
          href="/"
          aria-label="Movie and Show Quotes homepage"
        >
          <span className="brand-mark" aria-hidden="true">“</span>
          <span>Movie <span className="brand-amp">&amp;</span> Show Quotes</span>
        </a>
        <nav aria-label="Main navigation">
          <a href="/">Home</a>
        </nav>
      </header>

      <main className="signup-main">
        <section className="signup-card" aria-labelledby="signup-title">
          <div className="eyebrow"><span className="eyebrow-dot" /> Get started</div>
          <h1 id="signup-title" className="signup-title">Create your account.</h1>
          <p className="signup-description">
            Sign up to get started with Movie &amp; Show Quotes.
          </p>

          <form className="signup-form" onSubmit={submitSignup}>
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
              <span>Email <span className="signup-optional">(optional)</span></span>
              <input
                type="email"
                name="email"
                autoComplete="email"
                value={form.email}
                onChange={(event) => updateField("email", event.target.value)}
              />
            </label>
            <label className="signup-field">
              <span>Password</span>
              <input
                type="password"
                name="password1"
                autoComplete="new-password"
                required
                value={form.password1}
                onChange={(event) => updateField("password1", event.target.value)}
              />
            </label>
            <label className="signup-field">
              <span>Confirm password</span>
              <input
                type="password"
                name="password2"
                autoComplete="new-password"
                required
                value={form.password2}
                onChange={(event) => updateField("password2", event.target.value)}
              />
            </label>

            {error && <p className="signup-error" role="alert">{error}</p>}

            <button className="signup-submit" type="submit" disabled={loading}>
              {loading ? "Creating account…" : "Create account"}
            </button>
          </form>
        </section>
      </main>

      <footer className="site-footer">
        <a className="footer-brand" href="/">Movie <span>&amp;</span> Show Quotes</a>
        <span>For the love of a good story.</span>
      </footer>
    </div>
  );
}

export default SignupPage;
