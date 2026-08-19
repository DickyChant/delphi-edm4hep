#ifndef SKELANA_PSCHDC_HPP
#define SKELANA_PSCHDC_HPP

#include "skelana/mtrack.hpp"

namespace skelana
{
/**                             Hadron identification based on
*                             combined RICH & TPC probabilities
*
*     NHAIDC                - Number of identified hadrons
*     LNHADC                - Length of the had. id. information
*     QHAIDC(LNHADC,MTRACK) - Real    array of HAIDC information
*     KHAIDC(LNHADC,MTRACK) - Integer array of HAIDC information
*
*     KHAIDC(1,I) - Pion   tag
*     KHAIDC(2,I) - Kaon   tag 
*     KHAIDC(3,I) - Proton tag
*     KHAIDC(4,I) - Heavy  tag
*     KHAIDC(5,I) - Electron  tag
*                  -1 - no information available
*                   0 - not a    pion/kaon/proton/heavy/electron
*                   1 - loose    pion/kaon/proton/heavy/electron
*                   2 - standard pion/kaon/proton/heavy/electron
*                   3 - tight    pion/kaon/proton/heavy/electron
*     KHAIDC(6,I) - Selection flag
*                  -1 - no information available
*                   bit 1 - liquid O.K.
*                   bit 2 - gas    O.K.
*                   bit 3 - TPC    O.K.
*
*/
    inline const int LNHADC = 6;
    extern "C" struct
    {
        int nhaidc;
        int khaidc[MTRACK][LNHADC];
    } pschdc_;

    inline int &NHAIDC = pschdc_.nhaidc;
    inline int &KHAIDC(int i, int j) { return pschdc_.khaidc[j - 1][i - 1]; }
} // namespace skelana

#endif // SKELANA_PSCHDC_HPP