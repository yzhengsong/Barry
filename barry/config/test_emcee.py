from barry.config.base import setup
from barry.framework.fitter import Fitter
from barry.framework.models.test import TestModel
from barry.framework.datasets.test import TestDataset
from barry.framework.samplers.ensemble import EnsembleSampler

if __name__ == "__main__":
    pfn, dir_name, file = setup(__file__)

    model = TestModel()
    data = TestDataset()

    sampler = EnsembleSampler(num_walkers=10, num_steps=1000, num_burn=300, temp_dir=dir_name)

    fitter = Fitter(dir_name)
    fitter.set_models(model)
    fitter.set_data(data)
    fitter.set_sampler(sampler)
    fitter.set_num_walkers(2)
    fitter.fit(file)

    if fitter.is_laptop():  # As I'm not sure if the cluster has matplotlib
        from chainconsumer import ChainConsumer
        res, = fitter.load()

        posterior, weight, chain, model, data = res
        c = ChainConsumer()
        c.add_chain(chain, weights=weight, parameters=model.get_labels())
        c.plotter.plot(filename=pfn + "_contour.png")