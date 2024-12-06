'''
Rename This! - Tool for quickly renaming a large number of files.
Copyright (C) 2024 CleitinhoDEV

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

---

Rename This! - Ferramenta para renomear um grande quantidade de arquivos de forma rápida.
Copyright (C) 2024 CleitinhoDEV

Este programa é um software livre: você pode redistribuí-lo e/ou modificá-lo
sob os termos da Licença Pública Geral GNU, conforme publicada pela
Free Software Foundation, na versão 3 da Licença, ou (a seu critério) qualquer versão posterior.

Este programa é distribuído na esperança de que seja útil,
mas SEM QUALQUER GARANTIA; sem mesmo a garantia implícita de
COMERCIABILIDADE ou ADEQUAÇÃO A UM DETERMINADO PROPÓSITO. Consulte a
Licença Pública Geral GNU para mais detalhes.

Você deve ter recebido uma cópia da Licença Pública Geral GNU
junto com este programa. Caso contrário, veja <https://www.gnu.org/licenses/>.
'''

import customtkinter as ctk
import os
from tkinter import filedialog, messagebox
import threading
import datetime
import webbrowser


# Função para abrir o seletor de pastas e preencher a caixa de texto com o caminho
def selecionar_pasta():
    pasta = filedialog.askdirectory(title="Choose the folder with the files")
    if pasta:
        entrada_pasta.delete(0, ctk.END)
        entrada_pasta.insert(0, pasta)


# Função para verificar se uma caixa está selecionada
def verificar_selecao():
    if not checkbox_123_var.get() and not checkbox_abc_var.get() and not checkbox_data_var.get():
        messagebox.showerror("Error", "Select a pattern")
        return False
    return True


# Função para exibir a tela de carregamento centralizada
def mostrar_tela_carregamento():
    tela_carregamento = ctk.CTkToplevel(root)
    tela_carregamento.title("Loading...")

    # Centralizar a tela de carregamento
    largura_tela = 300
    altura_tela = 150
    largura_janela = root.winfo_screenwidth()
    altura_janela = root.winfo_screenheight()
    pos_x = (largura_janela // 2) - (largura_tela // 2)
    pos_y = (altura_janela // 2) - (altura_tela // 2)
    tela_carregamento.geometry(f"{largura_tela}x{altura_tela}+{pos_x}+{pos_y}")

    tela_carregamento.transient(root)
    tela_carregamento.grab_set()

    label_carregando = ctk.CTkLabel(tela_carregamento, text="renaming files...")
    label_carregando.pack(pady=10)

    barra_progresso = ctk.CTkProgressBar(tela_carregamento, width=250)
    barra_progresso.pack(pady=10)
    barra_progresso.set(0)

    label_progresso = ctk.CTkLabel(tela_carregamento, text="0 files renamed.")
    label_progresso.pack(pady=10)

    tela_carregamento.update()

    return tela_carregamento, barra_progresso, label_progresso


# Função para converter índice em letras do padrão de colunas do Excel
def indice_para_letras(indice):
    letras = ""
    while indice >= 0:
        letras = chr(indice % 26 + 65) + letras
        indice = indice // 26 - 1
    return letras


# Funções de renomeação para cada opção
def renomear_sequencial(pasta, nome_base, arquivos, barra_progresso, label_progresso, total_arquivos):
    if nome_base == "":
        for i, arquivo in enumerate(arquivos, 1):
            novo_nome = f"{i}{os.path.splitext(arquivo)[1]}"
            caminho_antigo = os.path.join(pasta, arquivo)
            caminho_novo = os.path.join(pasta, novo_nome)
            os.rename(caminho_antigo, caminho_novo)
            barra_progresso.set(i / total_arquivos)
            label_progresso.configure(text=f"{i} files renamed.")
            label_progresso.update()
    else:
        for i, arquivo in enumerate(arquivos, 1):
            novo_nome = f"{nome_base}_{i}{os.path.splitext(arquivo)[1]}"
            caminho_antigo = os.path.join(pasta, arquivo)
            caminho_novo = os.path.join(pasta, novo_nome)
            os.rename(caminho_antigo, caminho_novo)
            barra_progresso.set(i / total_arquivos)
            label_progresso.configure(text=f"{i} files renamed.")
            label_progresso.update()

def renomear_alfabetico(pasta, nome_base, arquivos, barra_progresso, label_progresso, total_arquivos):
    if nome_base == "":
        for i, arquivo in enumerate(arquivos):
            sufixo = indice_para_letras(i)
            novo_nome = f"{sufixo}{os.path.splitext(arquivo)[1]}"
            caminho_antigo = os.path.join(pasta, arquivo)
            caminho_novo = os.path.join(pasta, novo_nome)
            os.rename(caminho_antigo, caminho_novo)
            barra_progresso.set((i + 1) / total_arquivos)
            label_progresso.configure(text=f"{i + 1} files renamed.")
            label_progresso.update()
    else:
        for i, arquivo in enumerate(arquivos):
            sufixo = indice_para_letras(i)
            novo_nome = f"{nome_base}_{sufixo}{os.path.splitext(arquivo)[1]}"
            caminho_antigo = os.path.join(pasta, arquivo)
            caminho_novo = os.path.join(pasta, novo_nome)
            os.rename(caminho_antigo, caminho_novo)
            barra_progresso.set((i + 1) / total_arquivos)
            label_progresso.configure(text=f"{i + 1} files renamed.")
            label_progresso.update()


def renomear_data(pasta, nome_base, arquivos, barra_progresso, label_progresso, total_arquivos):

    if nome_base == "":
        for i, arquivo in enumerate(arquivos):
            caminho_antigo = os.path.join(pasta, arquivo)

            # Obter a data de modificação original do arquivo
            data_modificacao = datetime.datetime.fromtimestamp(os.path.getmtime(caminho_antigo))

            # Formatar a data para evitar caracteres inválidos no nome do arquivo
            data_formatada = data_modificacao.strftime("%d-%m-%Y_%H-%M-%S")

            # Garantir que o nome do arquivo seja único, incluindo o índice
            novo_nome = f"{data_formatada}_{i + 1}{os.path.splitext(arquivo)[1]}"
            caminho_novo = os.path.join(pasta, novo_nome)

            try:
                # Renomear o arquivo
                os.rename(caminho_antigo, caminho_novo)

                # Atualizar a barra de progresso
                barra_progresso.set((i + 1) / total_arquivos)
                label_progresso.configure(text=f"{i + 1} files renamed.")
                label_progresso.update()

            except Exception as e:
                print(f"Error renaming the file {arquivo}: {e}")
    else:
        for i, arquivo in enumerate(arquivos):
            caminho_antigo = os.path.join(pasta, arquivo)

            # Obter a data de modificação original do arquivo
            data_modificacao = datetime.datetime.fromtimestamp(os.path.getmtime(caminho_antigo))

            # Formatar a data para evitar caracteres inválidos no nome do arquivo
            data_formatada = data_modificacao.strftime("%d-%m-%Y_%H-%M-%S")

            # Garantir que o nome do arquivo seja único, incluindo o índice
            novo_nome = f"{nome_base}_{data_formatada}_{i + 1}{os.path.splitext(arquivo)[1]}"
            caminho_novo = os.path.join(pasta, novo_nome)

            try:
                # Renomear o arquivo
                os.rename(caminho_antigo, caminho_novo)

                # Atualizar a barra de progresso
                barra_progresso.set((i + 1) / total_arquivos)
                label_progresso.configure(text=f"{i + 1} files renamed.")
                label_progresso.update()

            except Exception as e:
                print(f"Error renaming the file {arquivo}: {e}")


# Função principal para renomear arquivos conforme a seleção
def renomear_arquivos():
    if not verificar_selecao():
        return

    pasta = entrada_pasta.get()
    nome_base = entrada_renomear.get()
    arquivos = [f for f in os.listdir(pasta) if os.path.isfile(os.path.join(pasta, f))]

    tela_carregamento, barra_progresso, label_progresso = mostrar_tela_carregamento()

    # Contar o número total de arquivos antes de iniciar
    total_arquivos = len(arquivos)

    try:
        if checkbox_123_var.get():
            renomear_sequencial(pasta, nome_base, arquivos, barra_progresso, label_progresso, total_arquivos)
        elif checkbox_abc_var.get():
            renomear_alfabetico(pasta, nome_base, arquivos, barra_progresso, label_progresso, total_arquivos)
        elif checkbox_data_var.get():
            renomear_data(pasta, nome_base, arquivos, barra_progresso, label_progresso, total_arquivos)
    finally:
        tela_carregamento.destroy()

    # Mensagem final com a quantidade de arquivos renomeados
    messagebox.showinfo("Success", f"{total_arquivos} files renamed!")


# Função para garantir que apenas uma caixa de seleção esteja ativa
def selecionar_unico_checkbox(checkbox_var):
    checkbox_123_var.set(False)
    checkbox_abc_var.set(False)
    checkbox_data_var.set(False)
    checkbox_var.set(True)


# Função para abrir o link
def abrir_link():
    url = "https://www.bugzinho.com/renamethis"
    webbrowser.open(url)


# Criando a janela principal
root = ctk.CTk()
root.title("Rename This!")

root.iconbitmap("Design/icone.ico")

# Definir o tamanho da janela
window_width = 620
window_height = 150

# Obter as dimensões da tela
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()

# Calcular a posição para centralizar a janela
x = (screen_width - window_width) // 2
y = (screen_height - window_height) // 2

# Definir o tamanho da janela e travar o redimensionamento
root.geometry(f"{window_width}x{window_height}+{x}+{y}")  # Tamanho fixo e centralizado
root.resizable(False, False)  # Impede o redimensionamento

# Frame

borda_botoes = ctk.CTkFrame(
        root,
        corner_radius=10,
        border_width=2,
        border_color='Black',
        width=610,
        height=140,
        fg_color='#151515')
borda_botoes.place(x=5, y=5)

# Label e entrada de pasta
label = ctk.CTkLabel(root, text="Select the folder:", bg_color='#151515')
label.place(x=10, y=20)  # Define a posição (x=10, y=20)

entrada_pasta = ctk.CTkEntry(root, width=300, bg_color='#151515')
entrada_pasta.place(x=120, y=20)  # Define a posição (x=150, y=20)

botao_buscar = ctk.CTkButton(root, text="Search", command=selecionar_pasta,
                             fg_color="#483d8b", hover_color="#2c226a",
                             bg_color='#151515')
botao_buscar.place(x=430, y=20)  # Define a posição (x=460, y=20)

# Label e entrada de renomear
label_renomear = ctk.CTkLabel(root, text="Rename to:", bg_color='#151515')
label_renomear.place(x=10, y=60)

entrada_renomear = ctk.CTkEntry(root, width=300, bg_color='#151515')
entrada_renomear.place(x=120, y=60)

# Checkboxes
checkbox_123_var = ctk.BooleanVar()
checkbox_abc_var = ctk.BooleanVar()
checkbox_data_var = ctk.BooleanVar()

checkbox_123 = ctk.CTkCheckBox(root, text="123", variable=checkbox_123_var,
                               command=lambda: selecionar_unico_checkbox(checkbox_123_var),
                               fg_color="#483d8b", hover_color="#2c226a", bg_color='#151515')
checkbox_123.place(x=430, y=62)

checkbox_abc = ctk.CTkCheckBox(root, text="abc", variable=checkbox_abc_var,
                               command=lambda: selecionar_unico_checkbox(checkbox_abc_var),
                               fg_color="#483d8b", hover_color="#2c226a", bg_color='#151515')
checkbox_abc.place(x=490, y=62)

checkbox_data = ctk.CTkCheckBox(root, text="data", variable=checkbox_data_var,
                                command=lambda: selecionar_unico_checkbox(checkbox_data_var),
                                fg_color="#483d8b", hover_color="#2c226a", bg_color='#151515', width=60)
checkbox_data.place(x=550, y=62)

# Botão "Renomear"
botao_renomear = ctk.CTkButton(root, text="Rename",
                               command=lambda: threading.Thread(target=renomear_arquivos).start(),
                               fg_color="#483d8b", hover_color="#2c226a", bg_color='#151515')
botao_renomear.place(x=200, y=100)

# Botão "Ajuda"

botao_help = ctk.CTkButton(root, text="?",
                           command=lambda: threading.Thread(target=abrir_link).start(),
                           fg_color="#483d8b", hover_color="#2c226a", width=30, bg_color='#151515')
botao_help.place(x=575, y=20)

root.mainloop()
