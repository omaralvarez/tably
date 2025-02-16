from gentab.utils import console, ProgressBar
from gentab import SEED

import os
from pathlib import Path
from typing import Any, Literal, Optional, Union, cast, Tuple, Dict, List

import pandas as pd
import dask.dataframe as dd
import numpy as np
import torch
import sklearn.datasets
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
from sklearn.model_selection import train_test_split
from scipy.stats import wasserstein_distance, entropy
from scipy.spatial.distance import jensenshannon
from dython.nominal import theils_u
from imblearn.datasets import fetch_datasets
from ucimlrepo import fetch_ucirepo


class Dataset:
    def __init__(
        self,
        config,
        cache_path="datasets",
        labels=None,
        bins=None,
        n_partitions=5,
        oversample=0,
    ) -> None:
        self.config = config
        self.cache_path = cache_path
        self.labels = labels
        self.bins = bins
        self.n_partitions = n_partitions
        self.X_gen = None
        self.y_gen = None

        with ProgressBar(indeterminate=True).progress as p:
            gen_task = p.add_task(
                "Loading dataset {}...".format(self.config["name"]), total=None
            )

            if not self.config.exists("download"):
                self.load_path()
            else:
                if self.config["download"] == "ucimlrepo":
                    self.download_uci()
                elif self.config["download"] == "sklearn":
                    self.download_sklearn()
                else:
                    self.download_imb()

            if oversample:
                self.oversample(oversample)

            self.get_label_encoders()
            self.compute_categories()
            self.get_min_max()

        console.print("✅ Dataset loaded...")

    def __str__(self) -> str:
        return self.config["name"]

    def oversample(self, multiplier: int) -> None:
        self.X = pd.concat([self.X] * multiplier, ignore_index=True)
        self.y = pd.concat([self.y] * multiplier, ignore_index=True)

    def reset_indexes(self) -> None:
        # Reset indexes
        self.X.reset_index(drop=True, inplace=True)
        self.X_val.reset_index(drop=True, inplace=True)
        self.X_test.reset_index(drop=True, inplace=True)
        self.y.reset_index(drop=True, inplace=True)
        self.y_val.reset_index(drop=True, inplace=True)
        self.y_test.reset_index(drop=True, inplace=True)

    def load_path(self) -> None:
        self.X = pd.read_csv(self.config["path_X"])
        self.y = pd.read_csv(self.config["path_y"])
        self.X_test = pd.read_csv(self.config["path_X_test"])
        self.y_test = pd.read_csv(self.config["path_y_test"])

        self.X, self.X_val, self.y, self.y_val = train_test_split(
            self.X,
            self.y,
            test_size=self.config["val_size"],
            random_state=SEED,
            stratify=self.y,
        )

    def download_imb(self) -> None:
        Path(self.cache_path).mkdir(parents=True, exist_ok=True)

        data = fetch_datasets(
            filter_data=(self.config["name"],),
            data_home=self.cache_path,
            random_state=SEED,
        )[self.config["name"]]

        features = pd.DataFrame(
            data=data.data,
            columns=["f" + str(i + 1) for i in range(data.data.shape[1])],
        )
        labels = pd.DataFrame({self.config["y_label"]: data.target})

        self.X, self.X_test, self.y, self.y_test = train_test_split(
            features,
            labels,
            test_size=1 - self.config["train_size"],
            random_state=SEED,
            stratify=labels,
        )
        self.X_val, self.X_test, self.y_val, self.y_test = train_test_split(
            self.X_test,
            self.y_test,
            test_size=self.config["test_size"]
            / (self.config["test_size"] + self.config["val_size"]),
            random_state=SEED,
            stratify=self.y_test,
        )

        self.reset_indexes()

        self.config["binary_columns"] = self.X.columns.values.tolist()
        self.config["categorical_columns"] = []
        self.config["integer_columns"] = []

    def download_sklearn(self) -> None:
        try:
            sk = getattr(sklearn.datasets, "fetch_" + self.config["name"])(
                as_frame=True
            )
        except Exception:
            sk = getattr(sklearn.datasets, "load_" + self.config["name"])(as_frame=True)

        # metadata
        console.print(sk.DESCR)

        sk.frame.fillna("Missing", inplace=True)

        if self.labels is not None:
            sk.frame[self.config["y_label"]] = pd.cut(
                sk.frame[self.config["y_label"]],
                labels=self.labels,
                bins=self.bins,
            ).astype(str)

        self.X, self.X_test, self.y, self.y_test = train_test_split(
            sk.frame.loc[:, sk.frame.columns != self.config["y_label"]],
            sk.frame.loc[:, [self.config["y_label"]]],
            test_size=1 - self.config["train_size"],
            random_state=SEED,
            stratify=sk.frame.loc[:, [self.config["y_label"]]],
        )
        self.X_val, self.X_test, self.y_val, self.y_test = train_test_split(
            self.X_test,
            self.y_test,
            test_size=self.config["test_size"]
            / (self.config["test_size"] + self.config["val_size"]),
            random_state=SEED,
            stratify=self.y_test,
        )

        self.reset_indexes()

    def download_uci(self) -> None:
        Path(os.path.join(self.cache_path, "uci")).mkdir(parents=True, exist_ok=True)

        path_features = os.path.join(
            self.cache_path, "uci", self.config["name"] + "_features.csv"
        )
        path_targets = os.path.join(
            self.cache_path, "uci", self.config["name"] + "_targets.csv"
        )

        if Path(path_features).is_file() and Path(path_targets).is_file():
            features = pd.read_csv(path_features)
            targets = pd.read_csv(path_targets)
        else:
            uci = fetch_ucirepo(name=self.config["name"])

            # metadata
            console.print(uci.variables)

            uci.data.features.fillna("Missing", inplace=True)

            uci.data.features.to_csv(path_features, index=False)
            uci.data.targets.to_csv(path_targets, index=False)

            features = uci.data.features
            targets = uci.data.targets

        if self.labels is not None:
            targets = pd.cut(
                targets,
                labels=self.labels,
                bins=self.bins,
            ).astype(str)

        self.X, self.X_test, self.y, self.y_test = train_test_split(
            features,
            targets,
            test_size=1 - self.config["train_size"],
            random_state=SEED,
            stratify=targets,
        )
        self.X_val, self.X_test, self.y_val, self.y_test = train_test_split(
            self.X_test,
            self.y_test,
            test_size=self.config["test_size"]
            / (self.config["test_size"] + self.config["val_size"]),
            random_state=SEED,
            stratify=self.y_test,
        )

        self.reset_indexes()

    def save_to_disk(self, generator, tuner="") -> None:
        with ProgressBar(indeterminate=True).progress as p:
            gen_task = p.add_task(
                "Saving dataset to {}...".format(self.config["save_path"]), total=None
            )

            if tuner == "":
                path = self.config["save_path"]
            else:
                path = self.config["save_path"] + "_" + str(tuner).lower()

            Path(path).mkdir(parents=True, exist_ok=True)

            self.X_gen.to_csv(
                os.path.join(path, "X_gen_" + str(generator) + ".csv"),
                index=False,
            )
            self.y_gen.to_csv(
                os.path.join(path, "y_gen_" + str(generator) + ".csv"),
                index=False,
            )

        console.print("✅ Dataset saved to {}...".format(path))

    def load_from_disk(self, generator, tuner="") -> None:
        with ProgressBar(indeterminate=True).progress as p:
            gen_task = p.add_task("Loading dataset {}...".format(generator), total=None)

            if tuner == "":
                path = self.config["save_path"]
            else:
                path = self.config["save_path"] + "_" + str(tuner).lower()

            self.X_gen = pd.read_csv(
                os.path.join(path, "X_gen_" + str(generator) + ".csv")
            )
            self.y_gen = pd.read_csv(
                os.path.join(path, "y_gen_" + str(generator) + ".csv")
            )

        console.print(
            "✅ {} dataset loaded from {}...".format(
                generator, os.path.join(path, "*_" + str(generator) + ".csv")
            )
        )

    def compute_categories(self) -> None:
        self.cats = self.config["categorical_columns"] + self.config["binary_columns"]
        self.X_cats = self.X[self.cats].copy()
        self.X_cats[self.cats] = self.X_cats[self.cats].apply(
            lambda col: pd.Categorical(col)
        )

    def get_min_max(self) -> None:
        self.mn = np.min(
            [
                self.encode_categories(self.X).min(),
                self.encode_categories(self.X_val).min(),
                self.encode_categories(self.X_test).min(),
            ],
            axis=0,
        )
        self.mx = np.max(
            [
                self.encode_categories(self.X).max(),
                self.encode_categories(self.X_val).max(),
                self.encode_categories(self.X_test).max(),
            ],
            axis=0,
        )

    def get_normalized_features(self, df: pd.DataFrame) -> pd.DataFrame:
        X_norm = df.copy()
        X_norm = (X_norm - self.mn) / (self.mx - self.mn)

        return X_norm

    # Returns categorical + binary, check compute_categories()
    def get_categories(self) -> list[str]:
        return self.cats

    def get_binary(self) -> list[str]:
        return self.config["binary_columns"]

    def get_continuous(self) -> list[str]:
        return self.X.columns.difference(
            self.cats + [self.config["y_label"]]
        ).values.tolist()

    def encode_categories(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.config.exists("download") and self.config["download"] == "imbalanced":
            # __________marks_______________
            return df
        else:
            X_enc = df.copy()
            X_enc[self.cats] = X_enc[self.cats].apply(
                lambda col: pd.Categorical(col).codes
            )

        return X_enc

    def decode_categories(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.config.exists("download") and self.config["download"] == "imbalanced":
            return df
        else:
            cat_columns = self.X_cats.select_dtypes(["category"]).columns
            df[cat_columns] = df[cat_columns].apply(
                lambda col: pd.Categorical.from_codes(
                    col, self.X_cats[col.name].cat.categories
                )
            )

        return df

    def merge_classes(self, merge: dict[str, list[str]]) -> None:
        for cls, labs in merge.items():
            self.y[self.y[self.config["y_label"]].isin(labs)] = cls
            self.y_val[self.y_val[self.config["y_label"]].isin(labs)] = cls
            self.y_test[self.y_test[self.config["y_label"]].isin(labs)] = cls

        self.get_label_encoders()

    def get_label_encoders(self) -> None:
        self.label_encoder = LabelEncoder()
        self.label_encoder.fit(self.y)
        self.label_encoder_ohe = OneHotEncoder(sparse_output=False)
        self.label_encoder_ohe.fit(self.y)

    def encode_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.label_encoder.transform(df)

    def decode_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.label_encoder.inverse_transform(df)

    def num_classes(self) -> int:
        return self.y[self.config["y_label"]].nunique()

    def num_features(self) -> int:
        return len(self.X.columns)

    def get_feature_names(self) -> list[str]:
        return self.X.columns.values.tolist()

    def class_names(self) -> list[str]:
        return self.y[self.config["y_label"]].unique().tolist()

    def class_counts(self) -> int:
        return self.y[self.config["y_label"]].value_counts()

    def min_class_count(self) -> int:
        return self.y[self.config["y_label"]].value_counts().min()

    def row_count(self) -> int:
        return len(self.X.index)

    def generated_class_counts(self) -> int:
        return self.y_gen.value_counts()

    def generated_row_count(self) -> int:
        return len(self.X_gen.index)

    def get_single_df(self) -> pd.DataFrame:
        return pd.concat([self.X, self.y], axis=1)

    def set_split_result(self, data) -> None:
        self.X_gen = data.loc[:, data.columns != self.config["y_label"]]
        self.y_gen = data[[self.config["y_label"]]]

    def get_random_class_rows(self, cls: str, n: int):
        compliant_rows = self.y[self.y[self.config["y_label"]] == cls]
        idx = compliant_rows.sample(n=n, random_state=SEED).index
        return self.X.loc[idx]

    def get_random_gen_class_rows(self, cls: str, n: int):
        compliant_rows = self.y_gen[self.y_gen[self.config["y_label"]] == cls]
        idx = compliant_rows.sample(n=n, random_state=SEED).index
        return self.X_gen.loc[idx]

    def get_class_rows(self, cls: str):
        compliant_rows = self.y[self.y[self.config["y_label"]] == cls]
        idx = compliant_rows.index
        return self.X.loc[idx]

    def get_gen_class_rows(self, cls: str):
        compliant_rows = self.y_gen[self.y_gen[self.config["y_label"]] == cls]
        idx = compliant_rows.index
        return self.X_gen.loc[idx]

    def get_train_samples(self):
        return len(self.X) + len(self.X_val)

    def get_test_samples(self):
        return len(self.X_test)

    def get_imbalance_ratio(self) -> float:
        # Count the number of instances in each class
        class_counts = self.y[self.config["y_label"]].value_counts()

        # Calculate the imbalance ratio relative to the majority class
        majority_class_count = (class_counts).max()

        return (majority_class_count / class_counts).max()

    def get_info(self) -> dict:
        return {
            "name": self.config["name"],
            "imbalance": self.get_imbalance_ratio(),
            "continuous": len(self.get_continuous()),
            "categorical": len(self.get_categories()),
            # "binary": len(self.get_binary()),
            "train_samples": self.get_train_samples(),
            "test_samples": self.get_test_samples(),
        }

    def reduce_size(self, class_percentages) -> None:
        for cls, percent in class_percentages.items():
            self.reduce_uniformly_randomly(
                self.y[self.config["y_label"]] == cls, percent
            )

    def create_bins(self, bins, labels) -> None:
        self.y[self.config["y_label"]] = pd.cut(
            self.y[self.config["y_label"]], bins=bins, labels=labels
        ).astype(str)

        self.y_val[self.config["y_label"]] = pd.cut(
            self.y_val[self.config["y_label"]], bins=bins, labels=labels
        ).astype(str)

        self.y_test[self.config["y_label"]] = pd.cut(
            self.y_test[self.config["y_label"]], bins=bins, labels=labels
        ).astype(str)

        self.get_label_encoders()

    def remove(self, rows_to_remove) -> None:
        # Remove the selected rows from the DataFrame
        self.X.drop(rows_to_remove, inplace=True)
        self.X.reset_index(drop=True, inplace=True)
        self.y.drop(rows_to_remove, inplace=True)
        self.y.reset_index(drop=True, inplace=True)

    def drop_first_n(self, n) -> None:
        # Get first rows index
        rows_to_remove = self.X.head(n).index

        self.remove(rows_to_remove)

    def reduce_uniformly_randomly(self, condition, percentage) -> None:
        """
        Removes a random subset of rows from a DataFrame based on a condition.

        Parameters:
        - df: pandas DataFrame.
        - condition: A boolean series indicating which rows comply with the condition.
        - percentage: Percentage of rows to remove that comply with the condition.
        """
        # Identify rows that comply with the condition
        compliant_rows = self.y[condition]

        # Calculate the number of rows to remove
        n_remove = int(len(compliant_rows) * percentage)

        # Randomly select rows to remove
        rows_to_remove = compliant_rows.sample(n=n_remove, random_state=SEED).index

        self.remove(rows_to_remove)

    def memory_usage_mb(self, df) -> float:
        return df.memory_usage().sum() / 1024**2

    def reduce_mem_df(self, df) -> None:
        for col in df.columns:
            col_type = self.X[col].dtype

            if col_type != object and col_type != "category":
                c_min = self.X[col].min()
                c_max = self.X[col].max()
                if str(col_type)[:3] == "int":
                    if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                        self.X[col] = self.X[col].astype(np.int8)
                    elif (
                        c_min > np.iinfo(np.int16).min
                        and c_max < np.iinfo(np.int16).max
                    ):
                        self.X[col] = self.X[col].astype(np.int16)
                    elif (
                        c_min > np.iinfo(np.int32).min
                        and c_max < np.iinfo(np.int32).max
                    ):
                        self.X[col] = self.X[col].astype(np.int32)
                    elif (
                        c_min > np.iinfo(np.int64).min
                        and c_max < np.iinfo(np.int64).max
                    ):
                        self.X[col] = self.X[col].astype(np.int64)
                else:
                    if (
                        c_min > np.finfo(np.float16).min
                        and c_max < np.finfo(np.float16).max
                    ):
                        self.X[col] = self.X[col].astype(np.float16)
                    elif (
                        c_min > np.finfo(np.float32).min
                        and c_max < np.finfo(np.float32).max
                    ):
                        self.X[col] = self.X[col].astype(np.float32)
                    else:
                        self.X[col] = self.X[col].astype(np.float64)
            else:
                self.X[col] = self.X[col].astype("category")

    def reduce_mem(self) -> None:
        """iterate through all the columns of a dataframe and modify the data type
        to reduce memory usage.
        """
        start_mem = (
            self.memory_usage_mb(self.X)
            + self.memory_usage_mb(self.X_val)
            + self.memory_usage_mb(self.X_test)
        )
        console.print("💾 Memory usage of dataframe is {:.2f} MB...".format(start_mem))

        with ProgressBar(indeterminate=True).progress as p:
            p.add_task("Reducing memory usage...", total=None)

            self.reduce_mem_df(self.X)
            self.reduce_mem_df(self.X_val)
            self.reduce_mem_df(self.X_test)

        end_mem = (
            self.memory_usage_mb(self.X)
            + self.memory_usage_mb(self.X_val)
            + self.memory_usage_mb(self.X_test)
        )
        console.print(
            "💾 Memory usage after optimization: {:.2f} MB...".format(end_mem)
        )
        console.print(
            "✅ Memory usage reduced by {:.1f}%...".format(
                100 * (start_mem - end_mem) / start_mem
            )
        )

    def reduce_mem_gen(self) -> None:
        """iterate through all the columns of a dataframe and modify the data type
        to reduce memory usage.
        """
        start_mem = self.memory_usage_mb(self.X_gen)
        console.print("💾 Memory usage of dataframe is {:.2f} MB...".format(start_mem))

        with ProgressBar(indeterminate=True).progress as p:
            p.add_task("Reducing memory usage...", total=None)

            self.reduce_mem_df(self.X_gen)

        end_mem = self.memory_usage_mb(self.X_gen)
        console.print(
            "💾 Memory usage after optimization: {:.2f} MB...".format(end_mem)
        )
        console.print(
            "💾 Memory usage reduced by {:.1f}%...".format(
                100 * (start_mem - end_mem) / start_mem
            )
        )

    def get_single_encoded_data(self):
        X_real = self.encode_categories(self.X)
        X_gen = self.encode_categories(self.X_gen)

        y_real = pd.Series(self.encode_labels(self.y), name=self.config["y_label"])
        y_gen = pd.Series(self.encode_labels(self.y_gen), name=self.config["y_label"])

        real_data = pd.concat([X_real, y_real], axis=1)
        gen_data = pd.concat([X_gen, y_gen], axis=1)

        return real_data, gen_data

    def theils_u_mat(self, df):
        # Compute Theil's U-statistics between each pair of columns
        cate_columns = df.shape[1]
        theils_u_mat = np.zeros((cate_columns, cate_columns))

        for i in range(cate_columns):
            for j in range(cate_columns):
                theils_u_mat[i, j] = theils_u(df.iloc[:, i], df.iloc[:, j])

        return theils_u_mat

    # See the post https://towardsdatascience.com/the-search-for-categorical-correlation-a1cf7f1888c9
    def correlation_ratio(self, categories, measurements):
        fcat, _ = pd.factorize(categories)
        cat_num = np.max(fcat) + 1
        y_avg_array = np.zeros(cat_num)
        n_array = np.zeros(cat_num)
        for i in range(0, cat_num):
            cat_measures = measurements[np.argwhere(fcat == i).flatten()]
            n_array[i] = len(cat_measures)
            y_avg_array[i] = np.average(cat_measures)
        y_total_avg = np.sum(np.multiply(y_avg_array, n_array)) / np.sum(n_array)
        numerator = np.sum(
            np.multiply(n_array, np.power(np.subtract(y_avg_array, y_total_avg), 2))
        )
        denominator = np.sum(np.power(np.subtract(measurements, y_total_avg), 2))
        if numerator == 0:
            eta = 0.0
        else:
            eta = numerator / denominator
        return eta

    def ratio_mat(self, df, continuous_columns, categorical_columns):
        rat_mat = pd.DataFrame(index=continuous_columns, columns=categorical_columns)

        if len(categorical_columns) == 0 or len(continuous_columns) == 0:
            return np.zeros(1)
        else:
            for cat_col in categorical_columns:
                for cont_col in continuous_columns:
                    rat_mat[cat_col][cont_col] = self.correlation_ratio(
                        df[cat_col], df[cont_col]
                    )
        return rat_mat.values

    def fillNa_cont(self, df):
        for col in df.columns:
            mean_values = df[col].mean()
            df[col].fillna(mean_values, inplace=True)
        return df

    def fillNa_cate(self, df):
        for col in df.columns:
            mode_values = df[col].mode()[0]
            df[col].fillna(mode_values, inplace=True)
        return df

    def compute_correlations(self, df):
        num_mat = pd.DataFrame(df[self.get_continuous()])
        cat_mat = pd.DataFrame(df[self.get_categories()])

        num_mat = self.fillNa_cont(num_mat)
        cat_mat = self.fillNa_cate(cat_mat)

        pearson_sub_matrix = np.corrcoef(num_mat, rowvar=False)
        theils_u_matrix = self.theils_u_mat(cat_mat)
        correl_ratio_mat = self.ratio_mat(
            df, self.get_continuous(), self.get_categories()
        )

        return (pearson_sub_matrix, theils_u_matrix, correl_ratio_mat)

    def get_correlations(self):
        with ProgressBar(indeterminate=True).progress as p:
            p.add_task(
                "Computing Pearson Correlation, Theil's U, and Correlation Ratio...",
                total=None,
            )
            real_data, gen_data = self.get_single_encoded_data()
            real_pear, real_theils, real_ratio = self.compute_correlations(real_data)
            gen_pear, gen_theils, gen_ratio = self.compute_correlations(gen_data)

        console.print(
            "✅ Pearson Correlation, Theil's U, and Correlation Ratio computation complete..."
        )

        return (
            np.linalg.norm(real_pear - gen_pear),
            np.linalg.norm(real_theils - gen_theils),
            np.linalg.norm(real_ratio - gen_ratio),
        )

    def get_pearson_correlation(self) -> pd.Series:
        real_data, gen_data = self.get_single_encoded_data()

        return (
            real_data.corr(method="pearson") - gen_data.corr(method="pearson")
        ).abs()

    def column_entropy(self, column):
        _, counts = np.unique(np.round(column), return_counts=True)

        return entropy(counts)

    def compute_distances_hits(self, thres_percent=0.3):
        with ProgressBar(indeterminate=True).progress as p:
            p.add_task("Computing distances and hits...", total=None)

            real_data, gen_data = self.get_single_encoded_data()

            # Convert DataFrames to Dask DataFrames
            real_ddf = dd.from_pandas(real_data, npartitions=self.n_partitions)
            gen_ddf = dd.from_pandas(gen_data, npartitions=self.n_partitions)

            real_array = real_ddf.compute().values
            fake_array = gen_ddf.compute().values

            def euclidean_distance(source, target, w=None):
                if w is None:
                    return np.sqrt(((source - target) ** 2).sum(axis=1))
                else:
                    return np.sqrt(
                        (((source - target) / w[np.newaxis, :]) ** 2).sum(axis=1)
                    )

            # Function to compute the minimum L2 distance for each row in syn_df with respect to real_df
            def min_l2_distance(row, real_array):
                distance_array = euclidean_distance(row.values, real_array)
                first, second = np.partition(distance_array, 1)[0:2]

                return [first, second] if first < second else [second, first]

            # Calculate the minimum L2 distance for each row in gen_df with respect to real_df
            gen_ddf[["s_r_l2_min_1", "s_r_l2_min_2"]] = gen_ddf.apply(
                min_l2_distance,
                axis=1,
                args=(real_array,),
                result_type="expand",
                meta={0: "f8", 1: "f8"},
            )

            # Convert the Dask DataFrame to a Pandas DataFrame
            synth_dists = gen_ddf.compute()[["s_r_l2_min_1", "s_r_l2_min_2"]]

            # Obtain range in columns to check for repeated samples within threshold
            thres = thres_percent * (real_data.max() - real_data.min())
            thres[self.get_categories() + [self.config["y_label"]]] = 0

            # Entropy weights for Epsilon Risk
            w = np.array([self.column_entropy(data) for _, data in real_data.items()])

            # Compute hits for Hitting Rate and distances for Epsilon Risk
            def min_dist_real_synth(row, real_array, fake_array, thres, w):
                fake_distance = row.values - fake_array
                hits = (np.abs(fake_distance) <= thres).all(axis=1)
                fake_distance = np.sqrt(
                    ((fake_distance / w[np.newaxis, :]) ** 2).sum(axis=1)
                )
                real_distance = euclidean_distance(row.values, real_array, w)
                first, second = np.partition(real_distance, 1)[0:2]
                min_real_dist = second if first < second else first

                return [hits.any(), fake_distance.min(), min_real_dist]

            real_ddf[["hit", "r_s_diff_min", "r_r_diff_min"]] = real_ddf.apply(
                min_dist_real_synth,
                axis=1,
                args=(
                    real_array,
                    fake_array,
                    thres.values,
                    w,
                ),
                result_type="expand",
                meta={0: "?", 1: "f8", 2: "f8"},
            )

            real_hits_diffs = real_ddf.compute()[
                ["hit", "r_s_diff_min", "r_r_diff_min"]
            ]

        console.print("✅ Distances and hits computation complete...")

        return synth_dists, real_hits_diffs

    def hitting_rate(self, stats):
        with ProgressBar(indeterminate=True).progress as p:
            p.add_task("Computing Hitting Rate...", total=None)

            hit_rate = stats["hit"].values.sum() / len(self.X)

        console.print("✅ Hitting Rate computation complete...")

        return hit_rate

    def epsilon_identifiability_risk(self, stats):
        with ProgressBar(indeterminate=True).progress as p:
            p.add_task("Computing Epsilon Identifiability Risk...", total=None)

            r_diff = stats["r_s_diff_min"] - stats["r_r_diff_min"]
            identifiability_value = np.sum(r_diff < 0) / len(self.X)

        console.print("✅ Epsilon Identifiability Risk computation complete...")

        return identifiability_value

    def mean_distance_closest_record(self, stats):
        with ProgressBar(indeterminate=True).progress as p:
            p.add_task("Computing mean Distance to Closest Record...", total=None)

            mean_dist_closest = stats["s_r_l2_min_1"].mean()

        console.print("✅ Mean Distance to Closest Record computation complete...")

        return mean_dist_closest

    def nearest_neighbor_distance_ratio(self, stats):
        with ProgressBar(indeterminate=True).progress as p:
            p.add_task("Computing Nearest Neighbor Distance Ratio...", total=None)

            nn_dist_ratio = np.mean(
                stats["s_r_l2_min_1"].values / stats["s_r_l2_min_2"].values
            )

        console.print("✅ Nearest Neighbor Distance Ratio computation complete...")

        return nn_dist_ratio

    def jensen_shannon_distance(self):
        with ProgressBar(indeterminate=True).progress as p:
            p.add_task("Computing Jensen Shannon Distance...", total=None)

            real_data, gen_data = self.get_single_encoded_data()
            real_data = real_data[self.get_categories()]
            gen_data = gen_data[self.get_categories()]

            distances = real_data.apply(lambda x: jensenshannon(x, gen_data[x.name]))

        console.print("✅ Jensen Shannon computation complete...")

        return distances

    def wasserstein_distance(self):
        with ProgressBar(indeterminate=True).progress as p:
            p.add_task("Computing Wasserstein Distance...", total=None)

            real_data, gen_data = self.get_single_encoded_data()
            real_data = real_data[self.get_continuous()]
            gen_data = gen_data[self.get_continuous()]

            distances = real_data.apply(
                lambda x: wasserstein_distance(x, gen_data[x.name])
            )

        console.print("✅ Wasserstein computation complete...")

        return distances
