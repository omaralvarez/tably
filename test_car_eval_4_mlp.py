from synthtab.generators import (
    ROS,
    SMOTE,
    ADASYN,
    TVAE,
    CTGAN,
    GaussianCopula,
    CopulaGAN,
    CTABGAN,
    CTABGANPlus,
    AutoDiffusion,
    ForestDiffusion,
    Tabula,
    GReaT,
)
from synthtab.evaluators import MLP
from synthtab.tuners import (
    SMOTETuner,
    ADASYNTuner,
    TVAETuner,
    CTGANTuner,
    GaussianCopulaTuner,
    CopulaGANTuner,
    CTABGANTuner,
    CTABGANPlusTuner,
    AutoDiffusionTuner,
    ForestDiffusionTuner,
    TabulaTuner,
    GReaTTuner,
)
from synthtab.data import Config, Dataset
from synthtab.utils import console

config = Config("configs/car_eval_4.json")

dataset = Dataset(config)

trials = 10

# console.print(dataset.class_counts(), dataset.row_count())
# generator = TVAE(dataset)
# evaluator = MLP(generator)
# tuner = TVAETuner(evaluator, trials)
# tuner.tune()
# tuner.save_to_disk()
# console.print(dataset.generated_class_counts(), dataset.generated_row_count())

# console.print(dataset.class_counts(), dataset.row_count())
# generator = CTGAN(dataset)
# evaluator = MLP(generator)
# tuner = CTGANTuner(evaluator, trials)
# tuner.tune()
# tuner.save_to_disk()
# console.print(dataset.generated_class_counts(), dataset.generated_row_count())

# console.print(dataset.class_counts(), dataset.row_count())
# generator = GaussianCopula(dataset)
# evaluator = MLP(generator)
# tuner = GaussianCopulaTuner(evaluator, trials)
# tuner.tune()
# tuner.save_to_disk()
# console.print(dataset.generated_class_counts(), dataset.generated_row_count())

# console.print(dataset.class_counts(), dataset.row_count())
# generator = CopulaGAN(dataset)
# evaluator = MLP(generator)
# tuner = CopulaGANTuner(evaluator, trials)
# tuner.tune()
# tuner.save_to_disk()
# console.print(dataset.generated_class_counts(), dataset.generated_row_count())

# console.print(dataset.class_counts(), dataset.row_count())
# generator = CTABGAN(
#     dataset,
#     test_ratio=0.10,
# )
# evaluator = MLP(generator)
# tuner = CTABGANTuner(evaluator, trials)
# tuner.tune()
# tuner.save_to_disk()
# console.print(dataset.generated_class_counts(), dataset.generated_row_count())

# console.print(dataset.class_counts(), dataset.row_count())
# generator = CTABGANPlus(
#     dataset,
#     test_ratio=0.10,
# )
# evaluator = MLP(generator)
# tuner = CTABGANPlusTuner(evaluator, trials)
# tuner.tune()
# tuner.save_to_disk()
# console.print(dataset.generated_class_counts(), dataset.generated_row_count())

console.print(dataset.class_counts(), dataset.row_count())
generator = AutoDiffusion(dataset)
evaluator = MLP(generator)
tuner = AutoDiffusionTuner(evaluator, trials)
tuner.tune()
tuner.save_to_disk()
console.print(dataset.generated_class_counts(), dataset.generated_row_count())

console.print(dataset.class_counts(), dataset.row_count())
generator = ForestDiffusion(dataset, n_jobs=1, duplicate_K=4, n_estimators=100)
evaluator = MLP(generator)
tuner = ForestDiffusionTuner(evaluator, trials)
tuner.tune()
tuner.save_to_disk()
console.print(dataset.generated_class_counts(), dataset.generated_row_count())

console.print(dataset.class_counts(), dataset.row_count())
generator = GReaT(
    dataset,
    epochs=15,
    max_length=1024,
    temperature=0.6,
    batch_size=32,
    max_tries_per_batch=4096,
    n_samples=8192,
)
evaluator = MLP(generator)
tuner = GReaTTuner(
    evaluator, trials, min_epochs=15, max_epochs=30, max_tries_per_batch=16384
)
tuner.tune()
tuner.save_to_disk()
console.print(dataset.generated_class_counts(), dataset.generated_row_count())

console.print(dataset.class_counts(), dataset.row_count())
generator = Tabula(
    dataset,
    epochs=15,
    max_length=1024,
    temperature=0.6,
    batch_size=32,
    max_tries_per_batch=4096,
    n_samples=8192,
)
evaluator = MLP(generator)
tuner = TabulaTuner(
    evaluator, trials, min_epochs=15, max_epochs=30, max_tries_per_batch=16384
)
tuner.tune()
tuner.save_to_disk()
console.print(dataset.generated_class_counts(), dataset.generated_row_count())
