import os
import random
import shutil
import tarfile
import warnings

import requests
import torchvision
import torch.utils.data
from torchvision.datasets.utils import check_integrity
from tqdm import tqdm

from utils.constants import DATA_DIR

CALTECH_RAW = DATA_DIR / "Caltech_raw"
CALTECH_256 = DATA_DIR / "Caltech256"
CALTECH_10 = DATA_DIR / "Caltech10"

CALTECH_URL = "http://www.vision.caltech.edu/Image_Datasets/Caltech256/256_ObjectCategories.tar"
TAR_FILEPATH = CALTECH_RAW / CALTECH_URL.split('/')[-1]


def download():
    os.makedirs(CALTECH_RAW, exist_ok=True)
    if check_integrity(TAR_FILEPATH, md5="67b4f42ca05d46448c6bb8ecd2220f6d"):
        print(f"Using downloaded and verified {TAR_FILEPATH}")
    else:
        request = requests.get(CALTECH_URL, stream=True)
        total_size = int(request.headers.get('content-length', 0))
        wrote_bytes = 0
        with open(TAR_FILEPATH, 'wb') as f:
            for data in tqdm(request.iter_content(chunk_size=1024), desc=f"Downloading {CALTECH_URL}",
                             total=total_size // 1024,
                             unit='KB', unit_scale=True):
                wrote_bytes += f.write(data)
        if wrote_bytes != total_size:
            warnings.warn("Content length mismatch. Try downloading again.")
    print(f"Extracting {TAR_FILEPATH}")
    with tarfile.open(TAR_FILEPATH) as tar:
        tar.extractall(path=CALTECH_RAW)


def move_files(filepaths, folder_to):
    os.makedirs(folder_to, exist_ok=True)
    for filepath in filepaths:
        filepath.rename(folder_to / filepath.name)


def split_train_test(train_part=0.8):
    # we don't need noise/background class
    caltech_root = CALTECH_RAW / TAR_FILEPATH.stem
    shutil.rmtree(caltech_root / "257.clutter", ignore_errors=True)
    for category in caltech_root.iterdir():
        images = list(filter(lambda filepath: filepath.suffix == '.jpg', category.iterdir()))
        random.shuffle(images)
        n_train = int(train_part * len(images))
        images_train = images[:n_train]
        images_test = images[n_train:]
        move_files(images_train, CALTECH_256 / "train" / category.name)
        move_files(images_test, CALTECH_256 / "test" / category.name)
    print("Split Caltech dataset.")


def prepare_subset():
    """
    Prepares Caltech10 data subset.
    """
    subcategories = sorted(os.listdir(CALTECH_256 / "train"))[:10]
    for category in subcategories:
        for fold in ("train", "test"):
            shutil.copytree(CALTECH_256 / fold / category, CALTECH_10 / fold / category)


class Caltech256(torch.utils.data.TensorDataset):
    def __init__(self, train=True, root=CALTECH_256):
        fold = "train" if train else "test"
        self.root = root / fold
        self.prepare()
        self.transform_images()
        with open(self.transformed_data_path, 'rb') as f:
            data, targets = torch.load(f)
        super().__init__(data, targets)

    def prepare(self):
        if not CALTECH_256.exists():
            download()
            split_train_test()

    @property
    def transformed_data_path(self):
        return self.root.with_suffix('.pt')

    def transform_images(self):
        if self.transformed_data_path.exists():
            return
        transform = torchvision.transforms.Compose([
            torchvision.transforms.Resize(size=(224, 224)),
            torchvision.transforms.ToTensor(),
            torchvision.transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])
        dataset = torchvision.datasets.ImageFolder(root=self.root, transform=transform)
        loader = torch.utils.data.DataLoader(dataset, batch_size=32, num_workers=4)
        images_full = []
        labels_full = []
        for images, labels in tqdm(loader, desc=f"Applying image transform {self.root}"):
            images_full.append(images)
            labels_full.append(labels)
        images_full = torch.cat(images_full, dim=0)
        labels_full = torch.cat(labels_full, dim=0)
        with open(self.transformed_data_path, 'wb') as f:
            torch.save((images_full, labels_full), f)


class Caltech10(Caltech256):
    """
    Caltech256 first 10 classes subset.
    """

    def __init__(self, train=True):
        super().__init__(train=train, root=CALTECH_10)

    def prepare(self):
        super().prepare()
        if not CALTECH_10.exists():
            prepare_subset()
