#ifndef SKELANA_PSCELD_HPP
#define SKELANA_PSCELD_HPP

#include "skelana/mtrack.hpp"

namespace skelana
{
/*    +KEEP,PSCELD.                Electron Identification information
*                            ( PA extra-module ELID (25) )
*
*     NELID                - Number of tracks with ELID info    m s l
*     LENELD               - Length of information per electron
*     QELID(LENELD,MTRACK) - Real    array of elec. information
*     KELID(LENELD,MTRACK) - Integer array of elec. information
*
*     KELID(1,I) - Electron tag from ELECID :                   m s l
*                  0 - no identification run
*                  1 - identified NOT to be an electron
*                  2 - very loose electron
*                  3 - loose      electron
*                  4 - standard   electron
*                  5 - tight      electron
*     KELID(2,I) - Gamma conversion tag from ELECID (veto)      m s l
*                  1 - loose      electron
*                  2 - standard   electron
*                  3 - tight      electron
*     QELID(3,I) - Best estimate of electron Px at vertex       m s l
*     QELID(4,I) - Best estimate of electron Py at vertex       m s l
*     QELID(5,I) - Best estimate of electron Pz at vertex       m s l
*
*/
    inline const int LENELD = 5;
    extern "C" struct
    {
        int nelid;
        int kelid[MTRACK][LENELD];
    } psceld_;

    inline int &NELID = psceld_.nelid;
    inline int &KELID(int i, int j) { return psceld_.kelid[j - 1][i - 1]; }
    inline float &QELID(int i, int j) { return *reinterpret_cast<float *>(&psceld_.kelid[j - 1][i - 1]); }

} // namespace skelana

#endif // SKELANA_PSCELD_HPP