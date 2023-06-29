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
- [flake8](https://pypi.org/project/flake8/)
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
make flake8 
```


### formatting code
project uses:
- [isort](https://pypi.org/project/isort/)
- [black](https://pypi.org/project/black/)

lint checks will fail if the code is not formaated correctly

```shell
# make black will run both isort and black
make black
```


