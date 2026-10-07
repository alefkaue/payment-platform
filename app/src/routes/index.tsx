import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Astro" },
      { name: "description", content: "Acesse sua conta Astro." },
      { property: "og:title", content: "Astro" },
      { property: "og:description", content: "Pagamentos com split automático de IBS/CBS." },
    ],
  }),
  component: Index,
});

function Index() {
  const { ready, conta } = useAuth();
  if (!ready) return null;
  return <Navigate to={conta ? "/inicio" : "/bem-vindo"} replace />;
}
