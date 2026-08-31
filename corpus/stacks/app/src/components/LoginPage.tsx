import { useState, type FormEvent } from "react";
import { login } from "../auth";

interface LoginPageProps {
  onSignedIn?: () => void;
}

export function LoginPage({ onSignedIn }: LoginPageProps) {
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!login(user, pass)) {
      setError("Those credentials were not accepted.");
      return;
    }
    setError(null);
    if (onSignedIn) {
      onSignedIn();
    }
  };

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <h1>stacks</h1>
        <p className="login-lead">Oakhurst County Library System</p>

        <label htmlFor="login-user">User</label>
        <input
          id="login-user"
          type="text"
          autoComplete="off"
          value={user}
          onChange={(e) => setUser(e.target.value)}
        />

        <label htmlFor="login-pass">Password</label>
        <input
          id="login-pass"
          type="password"
          autoComplete="off"
          value={pass}
          onChange={(e) => setPass(e.target.value)}
        />

        {error && <p className="error-banner">{error}</p>}

        <button type="submit" className="btn btn-primary">
          Sign in
        </button>
        <p className="login-hint">
          Development credentials are dev / dev. This curtain is local only.
        </p>
      </form>
    </div>
  );
}
