import { useState, type SubmitEvent } from "react";
import Homepage from "./Homepage";
import LoginPage from "./LoginPage";
import ProfilePage from "./ProfilePage";
import SignupPage from "./SignupPage";
import type { Quote } from "./models";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function App() {
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path === "/login") return <LoginPage />;
  if (path === "/profile" || path === "/profile/api-keys") {
    return <ProfilePage />;
  }
  return path === "/signup" ? <SignupPage /> : <HomepageApp />;
}

function HomepageApp() {
  const [apiKey, setApiKey] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [username, setUsername] = useState<string | null>(
    () => document.getElementById("root")?.getAttribute("data-username") || null,
  );
  const [logoutLoading, setLogoutLoading] = useState(false);
  const [logoutError, setLogoutError] = useState("");

  async function logout() {
    setLogoutLoading(true);
    setLogoutError("");

    try {
      const csrfResponse = await fetch("/api/auth/csrf", {
        credentials: "same-origin",
      });
      if (!csrfResponse.ok) {
        throw new Error("Could not start logout. Please try again.");
      }

      const csrfData: unknown = await csrfResponse.json();
      if (!isRecord(csrfData) || typeof csrfData.csrfToken !== "string") {
        throw new Error("Could not start logout. Please try again.");
      }

      const response = await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfData.csrfToken },
      });
      if (!response.ok) {
        throw new Error("Could not log out. Please try again.");
      }

      setUsername(null);
    } catch (requestError) {
      setLogoutError(
        requestError instanceof Error
          ? requestError.message
          : "Could not log out. Please try again.",
      );
    } finally {
      setLogoutLoading(false);
    }
  }

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
      logoutLoading={logoutLoading}
      logoutError={logoutError}
      onLogout={logout}
    />
  );
}

export default App;