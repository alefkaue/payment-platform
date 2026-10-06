import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "PayFlow" },
      { name: "description", content: "Acesse sua conta PayFlow." },
      { property: "og:title", content: "PayFlow" },
      { property: "og:description", content: "Pagamentos com split automático de IBS/CBS." },
    ],
  }),
  component: Index,
});

function Index() {
  const { ready, conta } = useAuth();
  if (!ready) return null;
  return <Navigate to={conta ? "/inicio" : "/login"} replace />;
}
