"""Caminhos dos repos irmãos, num lugar só.

Antes disso, `DEFAULT_TIBIA_IDLE_DIR` estava copiado em três scripts e
`DEFAULT_CANARY_DIR` em dois — e os dois defaults estavam **errados**, não só
duplicados: o do tibia-idle resolvia para `<workspace>/tibia-idle/tibia-idle`
(uma pasta aninhada que não existe) e o do Canary era `C:\\canary-3.2.1`, um
caminho Windows num fluxo Linux-only. Na prática as flags eram obrigatórias e
ninguém tinha documentado isso.

Precedência: `--flag` > variável de ambiente > repo irmão no workspace.
"""

import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
REPO_DIR = os.path.dirname(EXTRACTOR_DIR)
# A pasta que contém este repo — é nela que os checkouts irmãos vivem.
WORKSPACE_DIR = os.path.dirname(REPO_DIR)


class MissingRepoError(Exception):
    """Diretório de repo irmão ausente, com o que fazer a respeito.

    Exceção própria (e não `FileNotFoundError`) de propósito: quem chama
    precisa distinguir "não configurado" de "arquivo sumiu no meio do
    pipeline" — o primeiro tem conserto óbvio, o segundo não.
    """


class SiblingRepo:
    def __init__(self, name: str, env_var: str, flag: str, sibling_dir: str):
        self.name = name
        self.env_var = env_var
        self.flag = flag
        self._sibling_dir = sibling_dir

    def sibling_default(self) -> str:
        """O irmão no workspace: `<workspace>/<nome>`, ao lado deste repo."""
        return os.path.join(WORKSPACE_DIR, self._sibling_dir)

    def resolve(self, from_flag=None) -> str:
        """Aplica a precedência, sem verificar se o caminho existe."""
        if from_flag:
            return from_flag

        from_env = os.environ.get(self.env_var)
        if from_env:
            return from_env

        return self.sibling_default()

    def require(self, from_flag=None) -> str:
        """Igual a `resolve`, mas exige que o diretório exista.

        A mensagem cita os três caminhos de configuração porque o erro aparece
        para quem acabou de clonar e não sabe que a dependência existe.
        """
        resolved = self.resolve(from_flag)
        if os.path.isdir(resolved):
            return resolved

        raise MissingRepoError(
            f"esperava um checkout do {self.name} em {resolved}; "
            f"passe {self.flag} ou defina {self.env_var}"
        )


TIBIA_IDLE = SiblingRepo(
    name="tibia-idle",
    env_var="TIBIA_IDLE_DIR",
    flag="--tibia-idle-dir",
    sibling_dir="tibia-idle",
)

CANARY = SiblingRepo(
    name="canary",
    env_var="CANARY_DIR",
    flag="--canary-dir",
    sibling_dir="canary",
)
