from functools import lru_cache

import numpy as np
import inspect
import os
import logging


# TODO: Add options for mnu, h0 default, omega_b, etc
# TODO: Calculate/Tabulate r_s alongside power spectra for different omega_m and hubble. We need this for eh98 smoothing of powerspectra


@lru_cache(maxsize=32)
def getCambGenerator(redshift=0.51, om_resolution=101, h0_resolution=1, h0=0.676, ob=0.04814, ns=0.97):
    return CambGenerator(redshift=redshift, om_resolution=om_resolution, h0_resolution=h0_resolution, h0=h0, ob=ob, ns=ns)


class CambGenerator(object):
    """ An object to generate power spectra using camb and save them to file.

    Useful because computing them in a likelihood step is insanely slow.
    """

    def __init__(self, redshift=0.61, om_resolution=101, h0_resolution=1, h0=0.676, ob=0.04814, ns=0.97):
        """ 
        Precomputes CAMB for efficiency. Access ks via self.ks, and use get_data for an array
        of both the linear and non-linear power spectrum
        """
        self.logger = logging.getLogger("barry")
        self.om_resolution = om_resolution
        self.h0_resolution = h0_resolution
        self.h0 = h0
        self.redshift = redshift

        self.data_dir = os.path.dirname(inspect.stack()[0][1]) + os.sep + "data/"
        hh = int(h0 * 10000)
        self.filename_unique = f"{int(self.redshift * 1000)}_{self.om_resolution}_{self.h0_resolution}_{hh}_{int(ob * 10000)}_{int(ns * 1000)}"
        self.filename = self.data_dir + f"cosmo_{self.filename_unique}.npy"

        self.k_min = 1e-4
        self.k_max = 5
        self.k_num = 2000
        self.ks = np.logspace(np.log(self.k_min), np.log(self.k_max), self.k_num, base=np.e)

        self.omch2s = np.linspace(0.05, 0.3, self.om_resolution)
        self.omega_b = ob
        self.ns = ns
        if h0_resolution == 1:
            self.h0s = [h0]
        else:
            self.h0s = np.linspace(0.6, 0.8, self.h0_resolution)

        self.data = None
        self.logger.info(f"Creating CAMB data with {self.om_resolution} x {self.h0_resolution}")

    def load_data(self, can_generate=False):
        if not os.path.exists(self.filename):
            if not can_generate:
                msg = "Data does not exist and this isn't the time to generate it!"
                self.logger.error(msg)
                raise ValueError(msg)
            else:
                self.data = self._generate_data()
        else:
            self.logger.info("Loading existing CAMB data")
            self.data = np.load(self.filename)

    @lru_cache(maxsize=512)
    def get_data(self, om=0.31, h0=None):
        """ Returns the sound horizon the linear power spectrum"""
        if h0 is None:
            h0 = self.h0
        if self.data is None:
            self.load_data()
        omch2 = (om - self.omega_b) * h0 * h0
        data = self._interpolate(omch2, h0)
        return data[0], data[1:]

    def _generate_data(self):
        self.logger.info(f"Generating CAMB data with {self.om_resolution} x {self.h0_resolution}")
        os.makedirs(self.data_dir, exist_ok=True)
        import camb

        pars = camb.CAMBparams()
        pars.set_dark_energy(w=-1.0, dark_energy_model="fluid")
        pars.InitPower.set_params(As=2.130e-9, ns=self.ns)
        pars.set_matter_power(redshifts=[self.redshift], kmax=self.k_max)
        self.logger.info("Configured CAMB power and dark energy")

        data = np.zeros((self.om_resolution, self.h0_resolution, 1 + self.k_num))
        for i, omch2 in enumerate(self.omch2s):
            for j, h0 in enumerate(self.h0s):
                self.logger.debug("Generating %d:%d  %0.3f  %0.3f" % (i, j, omch2, h0))
                pars.set_cosmology(
                    H0=h0 * 100,
                    omch2=omch2,
                    mnu=0.0,
                    ombh2=self.omega_b * h0 * h0,
                    omk=0.0,
                    tau=0.063,
                    neutrino_hierarchy="degenerate",
                    num_massive_neutrinos=1,
                )
                pars.NonLinear = camb.model.NonLinear_none
                results = camb.get_results(pars)
                params = results.get_derived_params()
                rdrag = params["rdrag"]
                kh, z, pk_lin = results.get_matter_power_spectrum(minkh=self.k_min, maxkh=self.k_max, npoints=self.k_num)
                data[i, j, 0] = rdrag
                data[i, j, 1:] = pk_lin
        self.logger.info(f"Saving to {self.filename}")
        np.save(self.filename, data)
        return data

    def _interpolate(self, omch2, h0):
        """ Performs bilinear interpolation on the entire pk array """
        omch2_index = 1.0 * (self.om_resolution - 1) * (omch2 - self.omch2s[0]) / (self.omch2s[-1] - self.omch2s[0])

        if self.h0_resolution == 1:
            h0_index = 0
        else:
            h0_index = 1.0 * (self.h0_resolution - 1) * (h0 - self.h0s[0]) / (self.h0s[-1] - self.h0s[0])

        x = omch2_index - np.floor(omch2_index)
        y = h0_index - np.floor(h0_index)

        data = self.data
        v1 = data[int(np.floor(omch2_index)), int(np.floor(h0_index))]  # 00
        v2 = data[int(np.ceil(omch2_index)), int(np.floor(h0_index))]  # 01

        if self.h0_resolution == 1:
            final = v1 * (1 - x) * (1 - y) + v2 * x * (1 - y)
        else:
            v3 = data[int(np.floor(omch2_index)), int(np.ceil(h0_index))]  # 10
            v4 = data[int(np.ceil(omch2_index)), int(np.ceil(h0_index))]  # 11
            final = v1 * (1 - x) * (1 - y) + v2 * x * (1 - y) + v3 * y * (1 - x) + v4 * x * y
        return final


def test_rand_h0const():
    g = CambGenerator()
    g.load_data()

    def fn():
        g.get_data(np.random.uniform(0.1, 0.2))

    return fn


def test_rand():
    g = CambGenerator()
    g.load_data()

    def fn():
        g.get_data(np.random.uniform(0.1, 0.2), h0=np.random.uniform(60, 80))

    return fn


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="[%(levelname)7s |%(funcName)15s]   %(message)s")
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    c = {"om": 0.31, "h0": 0.676, "z": 0.61, "ob": 0.04814, "ns": 0.97, "reconscale": 15}

    generator = CambGenerator(om_resolution=101, h0_resolution=1, h0=c["h0"], ob=c["ob"], ns=c["ns"], redshift=c["z"])
    generator.load_data(can_generate=True)
    # generator = CambGenerator()
    # generator = CambGenerator(om_resolution=50, h0_resolution=1)
    # generator = CambGenerator(om_resolution=10, h0_resolution=10)
    # generator = CambGenerator(om_resolution=50, h0_resolution=50)
    #
    # import timeit
    # n = 10000
    # print("Takes on average, %.1f microseconds" % (timeit.timeit(test_rand_h0const(), number=n) * 1e6 / n))
    # import matplotlib.pyplot as plt
    # plt.plot(generator.ks, generator.get_data(0.3)[1])
    # plt.plot(generator.ks, generator.get_data(0.2)[1])
    # plt.xscale("log")
    # plt.yscale("log")
    # plt.show()