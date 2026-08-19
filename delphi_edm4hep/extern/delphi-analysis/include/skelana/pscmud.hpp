#ifndef SKELANA_PSCMUD_HPP
#define SKELANA_PSCMUD_HPP

#include "skelana/mtrack.hpp"

namespace skelana
{
/*+KEEP,PSCMUD.                Muon Identification information
*                            ( PA extra-module MUID (24) )
*
*     NMUID                - Number of tracks with MUID info
*     LENMUD               - Length of the Muon Id information
*     QMUID(LENMUD,MTRACK) - Real    array of muon information
*     KMUID(LENMUD,MTRACK) - Integer array of muon information
*
*     KMUID(1,I) - Muon tag from MUCAL2
*     QMUID(2,I) - Global chi2 of very loose muon refit
*     KMUID(3,I) - Hit pattern with inefficiencies
*
*/
    inline const int LENMUD = 3;
    extern "C" struct
    {
        int nmuid;
        int kmuid[MTRACK][LENMUD];
    } pscmud_;

    inline int &NMUID = pscmud_.nmuid;
    inline int &KMUID(int i, int j) { return pscmud_.kmuid[j - 1][i - 1]; }
    inline float &QMUID(int i, int j) { return *reinterpret_cast<float *>(&pscmud_.kmuid[j - 1][i - 1]); }

} // namespace skelana

#endif // SKELANA_PSCMUD_HPP