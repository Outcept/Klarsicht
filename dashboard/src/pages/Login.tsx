import { useAuth } from "../auth";

export default function Login() {
  const { login, error } = useAuth();

  return (
    <div className="min-h-screen flex items-center justify-center bg-black text-white px-6">
      <div className="max-w-sm w-full text-center">
        <div className="mx-auto h-12 w-12 rounded-lg bg-white flex items-center justify-center mb-6">
          <span className="text-black text-xl font-bold leading-none">K</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight mb-2">Klarsicht</h1>
        <p className="text-sm text-[#888] mb-8">Sign in with your organization account</p>

        {error && (
          <div className="mb-4 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-left">
            <p className="text-xs font-medium text-red-400 mb-1">Sign-in failed</p>
            <p className="text-xs font-mono text-red-300/80 break-all">{error}</p>
          </div>
        )}

        <button
          onClick={login}
          className="w-full rounded-md bg-white text-black font-medium py-2.5 hover:bg-white/90 transition-colors"
        >
          Sign in with SSO
        </button>
      </div>
    </div>
  );
}
