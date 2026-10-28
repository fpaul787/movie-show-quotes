import { useState, type SubmitEvent } from "react";
import Homepage from "./Homepage";
import SignupPage from "./SignupPage";
import type { Quote } from "./models";

function App() {
  const path = window.location.pathname.replace(/\/+$/, "");
  return path === "/signup" ? <SignupPage /> : <HomepageApp />;
}

function HomepageApp() {
  const [apiKey, setApiKey] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
    />
  );
}

export default App;