# Contributing

## dependencies
tools used:
- make
- git
- [asdf version manager](https://asdf-vm.com/guide/getting-started.html)


## first run ...  

### install project tools
use asdf to ensure required tools are installed ... configured tools are in  [.tool-versions](.tool-versions)
```bash
cd ~/work/mesh-client
asdf plugin add python
asdf plugin add poetry
asdf install
```

### install git hooks
```shell
make refresh-hooks
```

## normal development

### create virtualenv and install python dependencies

```shell
make install
source .venv/bin/activate
```

### running tests

start the mesh-sandbox docker container
```shell
make up
```

```shell
make test
```

### testing multiple python versions
to test all python versions configured
```shell
make tox
```


### linting
project uses:
- [ruff](https://docs.astral.sh/ruff/)
- [mypy](https://pypi.org/project/mypy/)

run both with 
```shell
make lint
```
or individually with
```shell
make mypy
```
or
```shell
make ruff 
```


### formatting code
project uses:
- [black](https://pypi.org/project/black/)

lint checks will fail if the code is not formatted correctly

```shell
make black
```


### secrets
the git-secrets script will try and avoid accidental committing of secrets
patterns are excluded using  [.gitdisallowed](.gitdisallowed) and allow listed using  [.gitallowed](.gitallowed)
if the git hooks are registered `make refresh hooks`  then secrets will be scanned for in the [pre-commit hook](scripts/hooks/pre-commit.sh).
You can check for secrets / test patterns at any time though with
```shell
make check-secrets-all
```

