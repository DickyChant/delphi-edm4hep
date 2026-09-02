#ifndef SKELANA_PSCEMF_HPC_HAC_STIC_HPP
#define SKELANA_PSCEMF_HPC_HAC_STIC_HPP

#include "skelana/mtrack.hpp"

namespace skelana
{
  /* +KEEP,PSCEMF
   *                            ( PA extra-module EMNC (22) )
   */
  inline const int LENEMF = 8;
  extern "C" struct
  {
    int nemf;
    int kemf[MTRACK][LENEMF];
  } pscemf_;

  /* +KEEP,PSCHPC
   *                            ( PA extra-module EMNC (22) )
   */
  inline const int LENHPC = 8;
  extern "C" struct
  {
    int nhpc;
    int khpc[MTRACK][LENHPC];
  } pschpc_;

  /* +KEEP,PSCHAC
   *                            ( PA extra-module HCNC (23) )
   */
  inline const int LENHAC = 8;
  extern "C" struct
  {
    int nhac;
    int khac[MTRACK][LENHAC];
  } pschac_;

  /* +KEEP,PSCSTC
   *                            ( PA extra-module SSTC (33) )
   *
   * Layout follows stdcdes.car:1402-1436, the deck compiled into
   * libskelanaxx.a. The SKELANA manual section A.3.3 documents an older
   * six-word form and does not match the library; PSFSTC writes KSTIC(7..9)
   * at skelana.car:6412-6415.
   *
   *   QSTIC(1,I) energy   QSTIC(2,I) theta   QSTIC(3,I) phi
   *   KSTIC(4,I) number of towers
   *   KSTIC(5,I) charged tag, large veto
   *   KSTIC(6,I) charged tag, combined veto
   *   KSTIC(7,I) veto multiplicity side A
   *   KSTIC(8,I) veto multiplicity side B
   *   KSTIC(9,I) silicon strip vertex position
   *
   * Word 5 carries different values on the two fill paths: PSHSTC (shortDST)
   * uses -2 tight photon / -1 loose photon / 0 none / 1 electron, PSFSTC
   * (fullDST) uses SDVETO's 0..3. Only PSFSTC fills words 7 and 8.
   */
  inline const int LENSTC = 9;
  extern "C" struct
  {
    int nstic;
    int kstic[MTRACK][LENSTC];
  } pscstc_;

  inline int &NEMF = pscemf_.nemf;
  inline int &NHPC = pschpc_.nhpc;
  inline int &NHAC = pschac_.nhac;
  inline int &NSTIC = pscstc_.nstic;

  inline int &KEMF(int i, int j) { return pscemf_.kemf[j - 1][i - 1]; }
  inline float &QEMF(int i, int j) { return *reinterpret_cast<float *>(&pscemf_.kemf[j - 1][i - 1]); }

  inline int &KHPC(int i, int j) { return pschpc_.khpc[j - 1][i - 1]; }
  inline float &QHPC(int i, int j) { return *reinterpret_cast<float *>(&pschpc_.khpc[j - 1][i - 1]); }

  inline int &KHAC(int i, int j) { return pschac_.khac[j - 1][i - 1]; }
  inline float &QHAC(int i, int j) { return *reinterpret_cast<float *>(&pschac_.khac[j - 1][i - 1]); }

  inline int &KSTIC(int i, int j) { return pscstc_.kstic[j - 1][i - 1]; }
  inline float &QSTIC(int i, int j) { return *reinterpret_cast<float *>(&pscstc_.kstic[j - 1][i - 1]); }

}   // namespace skelana

#endif // SKELANA_PSCEMF_HPC_HAC_STIC_HPP
