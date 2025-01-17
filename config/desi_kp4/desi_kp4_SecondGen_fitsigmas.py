import sys

sys.path.append("..")
sys.path.append("../..")
from barry.samplers import NautilusSampler
from barry.config import setup
from barry.models import PowerBeutler2017, CorrBeutler2017
from barry.datasets.dataset_power_spectrum import PowerSpectrum_DESI_KP4
from barry.datasets.dataset_correlation_function import CorrelationFunction_DESI_KP4
from barry.fitter import Fitter
import numpy as np
import scipy as sp
import pandas as pd
from barry.models.model import Correction
from barry.utils import weighted_avg_and_cov
import matplotlib.pyplot as plt
from chainconsumer import ChainConsumer

# Config file to fit the abacus cutsky mock means for sigmas
if __name__ == "__main__":

    # Get the relative file paths and names
    pfn, dir_name, file = setup(__file__)

    # Set up the Fitting class and Dynesty sampler with 250 live points.
    fitter = Fitter(dir_name, remove_output=False)
    sampler = NautilusSampler(temp_dir=dir_name)

    colors = ["#CAF270", "#84D57B", "#4AB482", "#219180", "#1A6E73", "#234B5B", "#232C3B"]

    tracers = {"LRG": [[0.4, 0.6], [0.6, 0.8], [0.8, 1.1]], "ELG_LOP": [[0.8, 1.1], [1.1, 1.6]], "QSO": [[0.8, 2.1]]}
    reconsmooth = {"LRG": 10, "ELG_LOP": 10, "QSO": 20}

    allnames = []
    cap = "gccomb"
    ffa = "ffa"  # Flavour of fibre assignment. Can be "ffa" for fast fiber assign, or "complete"
    rpcut = False  # Whether or not to include the rpcut
    imaging = "default_FKP"  # What form of imaging systematics to use. Can be "default_FKP", "default_FKP_addSN", or "default_FKP_addRF"
    rp = f"{imaging}_rpcut2.5" if rpcut else f"{imaging}"
    for t in tracers:
        for i, zs in enumerate(tracers[t]):
            for r, recon in enumerate([None, "sym"]):
                name = f"DESI_SecondGen_sm{reconsmooth[t]}_{t.lower()}_{ffa}_{cap}_{zs[0]}_{zs[1]}_{rp}_xi.pkl"
                dataset_xi = CorrelationFunction_DESI_KP4(
                    recon=recon,
                    fit_poles=[0, 2],
                    min_dist=50.0,
                    max_dist=150.0,
                    realisation=None,
                    reduce_cov_factor=25,
                    datafile=name,
                )

                for n, n_poly in enumerate([[], [-2, -1, 0], [0, 2], [-2, 0, 2]]):

                    model = CorrBeutler2017(
                        recon=dataset_xi.recon,
                        isotropic=dataset_xi.isotropic,
                        marg="full",
                        fix_params=["om", "alpha", "epsilon"],
                        poly_poles=dataset_xi.fit_poles,
                        correction=Correction.NONE,
                        n_poly=n_poly,
                    )

                    # Load in a pre-existing BAO template
                    pktemplate = np.loadtxt("../../barry/data/desi_kp4/DESI_Pk_template.dat")
                    model.parent.kvals, model.parent.pksmooth, model.parent.pkratio = pktemplate.T

                    name = dataset_xi.name + f" mock mean n_poly=" + str(n)
                    fitter.add_model_and_dataset(model, dataset_xi, name=name, color=colors[i + 1])
                    allnames.append(name)

    # Submit all the job. We have quite a few (42), so we'll
    # only assign 1 walker (processor) to each. Note that this will only run if the
    # directory is empty (i.e., it won't overwrite existing chains)
    fitter.set_sampler(sampler)
    fitter.set_num_walkers(1)
    fitter.fit(file)

    # Everything below here is for plotting the chains once they have been run. The should_plot()
    # function will check for the presence of chains and plot if it finds them on your laptop. On the HPC you can
    # also force this by passing in "plot" as the second argument when calling this code from the command line.
    if fitter.should_plot():
        import logging

        logging.info("Creating plots")

        # Set up a ChainConsumer instance. Plot the MAP for individual realisations and a contour for the mock average
        plotnames = [f"{t.lower()}_{zs[0]}_{zs[1]}" for t in tracers for i, zs in enumerate(tracers[t])]
        datanames = [f"{t.lower()}_{ffa}_{cap}_{zs[0]}_{zs[1]}" for t in tracers for i, zs in enumerate(tracers[t])]
        print(datanames)
        c = [ChainConsumer() for i in range(len(datanames) * 2)]
        for posterior, weight, chain, evidence, model, data, extra in fitter.load():

            # Get the tracer bin, sigma bin and n_poly bin
            data_bin = datanames.index(extra["name"].split(" ")[3].lower())
            recon_bin = 0 if "Prerecon" in extra["name"] else 1
            poly_bin = int(extra["name"].split("n_poly=")[1].split(" ")[0])
            stats_bin = recon_bin * len(datanames) + data_bin
            print(extra["name"], data_bin, recon_bin, poly_bin, stats_bin)

            # Store the chain in a dictionary with parameter names
            df = pd.DataFrame(chain, columns=model.get_labels())

            # Get the MAP point and set the model up at this point
            model.set_data(data)
            r_s = model.camb.get_data()["r_s"]
            max_post = posterior.argmax()
            params = df.loc[max_post]
            params_dict = model.get_param_dict(chain[max_post])
            for name, val in params_dict.items():
                model.set_default(name, val)
            if poly_bin == 3:
                print(params_dict["sigma_nl_par"], params_dict["sigma_nl_perp"], params_dict["sigma_s"])

            # Get some useful properties of the fit, and plot the MAP model against the data if it's the mock mean
            plotname = f"{plotnames[data_bin]}_prerecon" if recon_bin == 0 else f"{plotnames[data_bin]}_postrecon"
            figname = "/".join(pfn.split("/")[:-1]) + "/" + plotname + f"_npoly={poly_bin}_bestfit.png"
            new_chi_squared, dof, bband, mods, smooths = model.simple_plot(
                params_dict, display=False, figname=figname, c=colors[data_bin + 1]
            )

            # Add the chain or MAP to the Chainconsumer plots
            extra.pop("realisation", None)
            extra.pop("name", None)
            c[stats_bin].add_chain(
                df, weights=weight, name=plotname + f"_npoly={poly_bin}", plot_contour=True, plot_point=False, show_as_1d_prior=False
            )

        for data_bin, data_name in enumerate(datanames):
            for recon_bin in range(2):
                stats_bin = recon_bin * len(datanames) + data_bin
                plotname = f"{plotnames[data_bin]}_prerecon" if recon_bin == 0 else f"{plotnames[data_bin]}_postrecon"

                c[stats_bin].configure(bins=20, sigmas=[0, 1])
                fig = c[stats_bin].plotter.plot(
                    parameters=["$\\Sigma_{nl,||}$", "$\\Sigma_{nl,\\perp}$", "$\\Sigma_s$"],
                    legend=True,
                )
                xvals = np.linspace(0.0, 20.0, 100)
                fig.get_axes()[3].plot(xvals, xvals / (1.0 + 0.8), color="k", linestyle=":", linewidth=1.3)
                fig.savefig(
                    fname="/".join(pfn.split("/")[:-1]) + "/" + plotname + "_contour.png",
                    bbox_inches="tight",
                    dpi=300,
                    pad_inches=0.05,
                )
                print(c[stats_bin].analysis.get_latex_table())
