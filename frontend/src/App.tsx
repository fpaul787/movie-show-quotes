import { useEffect, useState, type SubmitEvent } from "react";
import Homepage from "./Homepage";
import LoginPage from "./LoginPage";
import SignupPage from "./SignupPage";
import type { Quote } from "./models";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function App() {
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path === "/login") return <LoginPage />;
  return path === "/signup" ? <SignupPage /> : <HomepageApp />;
}

function HomepageApp() {
  const [apiKey, setApiKey] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    async function loadCurrentUser() {
      try {
        const response = await fetch("/api/auth/me", {
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error("Could not check login status.");
        }

        const data: unknown = await response.json();
        if (!isRecord(data) || !("user" in data)) {
          throw new Error("Could not check login status.");
        }

        if (data.user === null) {
          setUsername(null);
        } else if (isRecord(data.user) && typeof data.user.username === "string") {
          setUsername(data.user.username);
        } else {
          throw new Error("Could not check login status.");
        }
      } catch {
        setAuthError("Could not check login status.");
      } finally {
        setAuthChecked(true);
      }
    }

    void loadCurrentUser();
  }, []);

  async function fetchQuote(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!apiKey.trim()) {
      setError("Please enter an API key to try the endpoint.");
      return;
    }

    setLoading(true);
    setError("");
    setQuote(null);
    try {
      const response = await fetch("/quotes/random", {
        headers: { "X-API-Key": apiKey.trim() },
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error ?? `Request failed (${response.status}).`);
      }
      setQuote(data as Quote);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not reach the quotes API. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <Homepage
      apiKey={apiKey}
      onApiKeyChange={setApiKey}
      quote={quote}
      error={error}
      loading={loading}
      onFetchQuote={fetchQuote}
      username={username}
      authChecked={authChecked}
      authError={authError}
    />
  );
}

export default App;