import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center px-6">
      <div className="text-center">
        <p className="text-sm font-mono text-[#22c55e] mb-3">404</p>
        <h1 className="text-3xl font-semibold tracking-tight mb-2">Page not found</h1>
        <p className="text-sm text-[#888] mb-6">The page you're looking for doesn't exist.</p>
        <Link
          to="/"
          className="inline-block rounded-md bg-white text-black font-medium px-4 py-2 text-sm hover:bg-white/90 transition-colors"
        >
          Back to overview
        </Link>
      </div>
    </div>
  );
}
