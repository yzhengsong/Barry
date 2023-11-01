#!/bin/bash -l
#SBATCH -J test_emcee_mock_avg.py
#SBATCH -p sheffield
#SBATCH --array=1-1%4
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --nodes=1
#SBATCH --mem=8GB
#SBATCH -t 24:00:00
#SBATCH -o /home/smv22yz/Barry/config/examples/out_files/test_emcee_mock_avg.py.o%j
unset SLURM_CPU_BIND_LIST

IDIR=/home/smv22yz/Barry/config/examples
conda deactivate

module load Anaconda3/5.3.0
module load OpenMPI/4.0.3-GCC-9.3.0
module load CFITSIO/3.48-GCCcore-9.3.0
module load OpenBLAS/0.3.9-GCC-9.3.0
module load Python/3.8.2-GCCcore-9.3.0
source activate env3
#source /home/smv22yz/cosmo/code/planck/bin/clik_profile.sh

#conda activate env3
echo $PATH
echo "Activated python"
executable=$(which python)
echo $executable

PROG=test_emcee_mock_avg.py
PARAMS=`expr ${SLURM_ARRAY_TASK_ID} - 1`
cd $IDIR
sleep $((RANDOM % 5))
time $executable $PROG $PARAMS
