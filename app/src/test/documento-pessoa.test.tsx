import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DocumentoPessoa } from "@/components/payflow/documento-pessoa";

afterEach(cleanup);

it.each(["rg", "cnh", "cin"] as const)(
  "mantém frente e verso para %s no cadastro e perfil",
  (tipo) => {
    render(
      <DocumentoPessoa
        tipo={tipo}
        frente={null}
        verso={null}
        onTipo={vi.fn()}
        onFrente={vi.fn()}
        onVerso={vi.fn()}
      />,
    );
    expect(screen.getByText(/— frente/)).toBeTruthy();
    expect(screen.getByText(/— verso/)).toBeTruthy();
    expect(screen.getAllByLabelText("Tirar foto ou escolher")).toHaveLength(2);
  },
);

it("passaporte pede uma página e permite escolher outro tipo", () => {
  const onTipo = vi.fn();
  render(
    <DocumentoPessoa
      tipo="passaporte"
      frente={null}
      verso={null}
      onTipo={onTipo}
      onFrente={vi.fn()}
      onVerso={vi.fn()}
    />,
  );
  expect(screen.getByText("Página com a foto")).toBeTruthy();
  expect(screen.getAllByLabelText("Tirar foto ou escolher")).toHaveLength(1);
  fireEvent.change(screen.getByLabelText("Qual documento"), { target: { value: "cnh" } });
  expect(onTipo).toHaveBeenCalledWith("cnh");
});
