import { useEffect, useState, type ReactNode } from "react";
import { AUTH_EVENT, isAuthenticated } from "../auth";
import { LoginPage } from "./LoginPage";

interface AuthGateProps {
  children: ReactNode;
}

export function AuthGate({ children }: AuthGateProps) {
  const [signedIn, setSignedIn] = useState<boolean>(isAuthenticated());

  useEffect(() => {
    const sync = () => setSignedIn(isAuthenticated());
    window.addEventListener(AUTH_EVENT, sync);
    return () => window.removeEventListener(AUTH_EVENT, sync);
  }, []);

  if (!signedIn) {
    return <LoginPage />;
  }
  return <>{children}</>;
}
