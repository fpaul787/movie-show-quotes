import { useState, type SubmitEvent } from "react";
import type { Quote } from "./models";

type HomepageProps = {
  apiKey: string;
  onApiKeyChange: (apiKey: string) => void;
  quote: Quote | null;
  error: string;
  loading: boolean;
  onFetchQuote: (event: SubmitEvent<HTMLFormElement>) => void;
  username: string | null;
  logoutLoading: boolean;
  logoutError: string;
  onLogout: () => void;
};

function Homepage({
  apiKey,
  onApiKeyChange,
  quote,
  error,
  loading,
  onFetchQuote,
  username,
  logoutLoading,
  logoutError,
  onLogout,
}: HomepageProps) {
  const [copied, setCopied] = useState(false);
  const curlExample = [
    `curl ${window.location.origin}/quotes/random \\`,
    '  -H "X-API-Key: YOUR_API_KEY"',
  ].join("\n");

  async function copyExample() {
    try {
      await navigator.clipboard.writeText(curlExample);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
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
          <a className="nav-try" href="#try-it">Try the API. Please</a>
          {username ? (
            <>
              <a className="user-greeting" href="/profile/" title={username}>Hi {username}!</a>
              <button
                className="logout-button"
                type="button"
                onClick={onLogout}
                disabled={logoutLoading}
              >
                {logoutLoading ? "Logging out…" : "Log out"}
              </button>
            </>
          ) : (
            <>
              <a href="/login/">Log in</a>
              <a href="/signup/">Sign up</a>
            </>
          )}
          {logoutError && <span className="auth-error" role="alert">{logoutError}</span>}
        </nav>
      </header>

      <main>
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <div className="eyebrow"><span className="eyebrow-dot" /> Words that stay with you</div>
            <h1 id="hero-title">Every story<br />has a <em>line.</em></h1>
            <p className="hero-description">
              Bring the best of the big and small screen into your next project.
              One simple API, an endless supply of inspiration.
            </p>
            <div className="hero-actions">
              <a className="button button-primary" href="#try-it">Get a random quote <span aria-hidden="true">↗</span></a>
              <a className="button button-quiet" href="#quick-start">Explore the docs <span aria-hidden="true">↓</span></a>
            </div>
            <div className="hero-footnote"><span className="status-dot" /> Simple JSON. Ready when you are.</div>
          </div>

          <div className="showcase" aria-label="API preview">
            <div className="showcase-glow" />
            <div className="orbit orbit-one" /><div className="orbit orbit-two" />
            <div className="poster-card">
              <div className="poster-top"><span>THE QUOTE API</span><span className="poster-index">01 / ∞</span></div>
              <div className="poster-art" aria-hidden="true">
                <span className="art-line art-line-one" /><span className="art-line art-line-two" />
                <span className="art-sun" /><span className="art-horizon" />
                <span className="art-spark spark-one">✳</span><span className="art-spark spark-two">✳</span>
                <span className="art-caption">A NEW<br />PERSPECTIVE</span>
              </div>
              <div className="poster-bottom"><span>FILM · TELEVISION · STORIES</span><span className="poster-arrow">↗</span></div>
            </div>
            <div className="floating-chip chip-live"><span className="chip-pulse" /> LIVE API</div>
            <div className="floating-chip chip-json"><span className="json-brace">{ }</span> JSON</div>
            <div className="showcase-note">A little inspiration,<br />on demand.</div>
          </div>
        </section>

        <section className="try-section" id="try-it" aria-labelledby="try-title">
          <div className="section-heading">
            <div><div className="eyebrow">Make it yours</div><h2 id="try-title">Your next line is<br className="mobile-break" /> one request away.</h2></div>
            <p>Have an API key? Try a live request right here. Your key is only sent with this request and is never saved.</p>
          </div>
          <div className="try-grid">
            <form className="try-card" onSubmit={onFetchQuote}>
              <div className="card-topline"><span className="card-label">LIVE REQUEST</span><span className="request-method">GET</span></div>
              <div className="endpoint-line"><span className="endpoint-lock" aria-hidden="true">⌘</span><code>/quotes/random</code><span className="endpoint-ready">● ready</span></div>
              <label className="key-label" htmlFor="api-key">Your API key</label>
              <div className="key-row">
                <input
                  id="api-key"
                  type="password"
                  autoComplete="off"
                  placeholder="Paste your key here"
                  value={apiKey}
                  onChange={(event) => onApiKeyChange(event.target.value)}
                  aria-describedby="key-help request-feedback"
                />
                <button className="send-button" type="submit" disabled={loading}>
                  {loading ? "Fetching…" : "Send request"}<span aria-hidden="true">↗</span>
                </button>
              </div>
              <p className="key-help" id="key-help">Keys are not stored or logged by this page.</p>
              <div className={`request-feedback${error ? " has-error" : ""}`} id="request-feedback" aria-live="polite">
                {error && <><span aria-hidden="true">!</span> {error}</>}
                {quote && (
                  <div className="quote-result">
                    <span className="result-kicker">{quote.source} · {quote.year}</span>
                    <blockquote>“{quote.text}”</blockquote>
                    <span className="result-credit">{quote.character} <span>—</span> {quote.title}</span>
                    {quote.tags.length > 0 && <div className="tag-list">{quote.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
                  </div>
                )}
              </div>
            </form>

            <div className="code-card" id="quick-start">
              <div className="code-card-head"><span className="card-label">QUICK START</span><button type="button" className="copy-button" onClick={copyExample} aria-label="Copy curl example">{copied ? "Copied ✓" : "Copy ↗"}</button></div>
              <div className="code-window"><div className="window-dots" aria-hidden="true"><i /><i /><i /></div><pre><span className="code-muted">$</span> curl <span className="code-url">{window.location.origin}</span>/quotes/random \
  -H <span className="code-value">"X-API-Key: YOUR_API_KEY"</span></pre></div>
              <div className="code-foot"><span className="response-dot" /> Returns a random quote as JSON</div>
            </div>
          </div>
        </section>

        <section className="how-section" aria-label="How it works">
          <div className="how-item"><span className="how-number">01</span><span className="how-title">Make a request</span><span className="how-copy">One endpoint. No complicated setup.</span></div>
          <span className="how-divider" aria-hidden="true">✳</span>
          <div className="how-item"><span className="how-number">02</span><span className="how-title">Get inspired</span><span className="how-copy">A fresh quote, delivered as JSON.</span></div>
          <span className="how-divider" aria-hidden="true">✳</span>
          <div className="how-item"><span className="how-number">03</span><span className="how-title">Build something</span><span className="how-copy">Put a memorable line to good use.</span></div>
        </section>
      </main>

      <footer className="site-footer"><a className="footer-brand" href="/">Movie <span>&amp;</span> Show Quotes</a><span>For the love of a good story.</span></footer>
    </div>
  );
}

export default Homepage;