<div align="center">

![Logo](notebooks/images/icon67.png)

# Learnable AI

**以 PyTorch 實作，可供學習 AI 的各式深度學習應用。**

</div>

---


## 本地開發與環境設置

載下 repo：

```bash
export REPO=practical_ai
git clone https://github.com/leemengtaiwan/$REPO.git
cd $REPO
```

建立新的 [Anaconda](https://www.anaconda.com/) 環境並在該環境內安裝函式庫：

```bash
conda create -n $REPO python=3.6 -y
conda activate $REPO  # 或 source activate $REPO
pip install -r requirements.txt

conda install pytorch torchvision cudatoolkit=10.1 -c pytorch
conda install -c conda-forge opencv
```

安裝 Jupyter Lab：

```bash
conda install -c conda-forge jupyterlab -y
```


設置 [nbdev](https://github.com/fastai/nbdev) 環境並以 editable 的方式安裝此 package：

```bash
nbdev_install_git_hooks
nbdev_build_lib
pip install -e ".[dev]"
```

建立環境變數文件：

```bash
touch .env
echo 'export DATA_ROOT=data' >> .env
```
