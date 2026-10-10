import {
  ArrowUpRight,
  Bell,
  Building2,
  CircleHelp,
  CreditCard,
  FileText,
  Banknote,
  Home,
  ListOrdered,
  Plane,
  QrCode,
  Receipt,
  Scale,
  ShieldCheck,
  ShoppingBag,
  Split,
  User,
  Users,
  type LucideProps,
} from "lucide-react";
import type { ComponentType } from "react";
import type { TipoConta } from "./types";

export interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<LucideProps>;
  /** Descrição curta usada no menu "Mais". */
  hint?: string;
}

/** Barra principal (sidebar no desktop, barra inferior no mobile). */
const PRIMARIA_PF: NavItem[] = [
  { to: "/inicio", label: "Início", icon: Home },
  { to: "/pix", label: "Pix", icon: QrCode },
  { to: "/cartoes", label: "Cartões", icon: CreditCard },
  { to: "/extrato", label: "Extrato", icon: ListOrdered },
];
const PRIMARIA_PJ: NavItem[] = [
  { to: "/inicio", label: "Início", icon: Home },
  { to: "/transferir", label: "Pagar", icon: ArrowUpRight },
  { to: "/contas", label: "Contas", icon: FileText },
  { to: "/split", label: "Split", icon: Split },
];

/** Itens secundários — aparecem no menu "Mais" (mobile) e no rodapé da sidebar. */
const SECUNDARIA_PF: NavItem[] = [
  { to: "/split", label: "Entenda o split", icon: Split, hint: "O imposto da Reforma, explicado" },
  { to: "/notificacoes", label: "Notificações", icon: Bell, hint: "Avisos da sua conta" },
  {
    to: "/convites",
    label: "Convites de empresas",
    icon: Building2,
    hint: "Acesso a contas PJ que convidaram você",
  },
  { to: "/perfil", label: "Meu perfil", icon: User, hint: "Dados, documentos e dispositivos" },
  {
    to: "/seguranca",
    label: "Segurança",
    icon: ShieldCheck,
    hint: "Aparelhos, sessões e atividade",
  },
  { to: "/ajuda", label: "Ajuda", icon: CircleHelp, hint: "Dúvidas e suporte" },
];
const SECUNDARIA_PJ: NavItem[] = [
  { to: "/extrato", label: "Extrato", icon: ListOrdered, hint: "Entradas e saídas da empresa" },
  {
    to: "/equipe",
    label: "Equipe & alçadas",
    icon: Users,
    hint: "Quem acessa e quanto pode mover",
  },
  { to: "/folha", label: "Folha de pagamento", icon: Banknote, hint: "Funcionários e salários" },
  { to: "/pendentes", label: "Aprovações", icon: Scale, hint: "Operações aguardando 2º aprovador" },
  {
    to: "/cartoes",
    label: "Cartão corporativo",
    icon: CreditCard,
    hint: "Cartão virtual e travas",
  },
  { to: "/notificacoes", label: "Notificações", icon: Bell, hint: "Avisos e repasses" },
  { to: "/perfil", label: "Meu perfil", icon: User, hint: "Dados e dispositivos" },
  {
    to: "/seguranca",
    label: "Segurança",
    icon: ShieldCheck,
    hint: "Aparelhos, sessões e atividade",
  },
  { to: "/ajuda", label: "Ajuda", icon: CircleHelp, hint: "Dúvidas e suporte" },
];

/** Quem só consulta não vê atalho para movimentar (o servidor recusa de qualquer jeito). */
export function navPrimaria(tipo: TipoConta, papel?: string): NavItem[] {
  if (tipo !== "PJ") return PRIMARIA_PF;
  return papel === "consulta" ? PRIMARIA_PJ.filter((i) => i.to !== "/transferir") : PRIMARIA_PJ;
}
export function navSecundaria(tipo: TipoConta): NavItem[] {
  return tipo === "PJ" ? SECUNDARIA_PJ : SECUNDARIA_PF;
}

export { Bell, ShieldCheck, Receipt };
