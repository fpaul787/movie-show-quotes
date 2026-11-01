import { useEffect, useState } from "react";

type Profile = {
  username: string;
  email: string | null;
};

function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
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
  }, []);

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
        <section className="signup-card" aria-labelledby="profile-title">
          <div className="eyebrow"><span className="eyebrow-dot" /> Your account</div>
          <h1 id="profile-title" className="signup-title">Profile.</h1>

          {error && <p className="signup-error" role="alert">{error}</p>}
          {profile && (
            <dl className="signup-description">
              <dt>Username</dt>
              <dd>{profile.username}</dd>
              <dt>Email</dt>
              <dd>{profile.email ?? "Not provided"}</dd>
            </dl>
          )}
        </section>
      </main>

      <footer className="site-footer">
        <a className="footer-brand" href="/">Movie <span>&amp;</span> Show Quotes</a>
        <span>For the love of a good story.</span>
      </footer>
    </div>
  );
}

export default ProfilePage;
