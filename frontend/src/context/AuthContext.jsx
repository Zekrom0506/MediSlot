import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { clearTokens, loadTokens, onSessionExpired, saveTokens } from "../api/client";
import * as api from "../api/medislot";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    onSessionExpired(() => {
      setUser(null);
      navigate("/login?expired=1");
    });
  }, [navigate]);

  useEffect(() => {
    if (!loadTokens()) {
      setIsLoading(false);
      return;
    }
    api
      .fetchCurrentUser()
      .then(setUser)
      .catch(() => clearTokens())
      .finally(() => setIsLoading(false));
  }, []);

  const logIn = useCallback(async (email, password) => {
    const tokens = await api.login(email, password);
    saveTokens(tokens);
    setUser(tokens.user);
    return tokens.user;
  }, []);

  const signUp = useCallback(async (details) => {
    const tokens = await api.register(details);
    saveTokens(tokens);
    setUser(tokens.user);
    return tokens.user;
  }, []);

  const logOut = useCallback(() => {
    clearTokens();
    setUser(null);
    navigate("/login");
  }, [navigate]);

  const value = useMemo(
    () => ({ user, isLoading, logIn, signUp, logOut }),
    [user, isLoading, logIn, signUp, logOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}

export function homePathForRole(role) {
  if (role === "doctor") {
    return "/doctor";
  }
  if (role === "admin") {
    return "/admin";
  }
  return "/";
}
