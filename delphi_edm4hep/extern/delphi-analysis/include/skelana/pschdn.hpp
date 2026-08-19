#ifndef SKELANA_PSCHDN_HPP
#define SKELANA_PSCHDN_HPP

#include "skelana/mtrack.hpp"

namespace skelana
{
/*
*     Hadron identification tags :
*
*                             New hadron identification based on
*                             RICH gas & liquid, Cherenkov angle,
*                             number of photons and quality flag
*                             (no OD or FCB requirement).
*
*     NHAIDN                - Number of identified hadrons
*     LNHADN                - Length of the had. id. information
*     QHAIDN(LNHADN,MTRACK) - Real    array of HAIDN information
*     KHAIDN(LNHADN,MTRACK) - Integer array of HAIDN information
*
*     KHAIDN(1,I) - Pion   tag
*     KHAIDN(2,I) - Kaon   tag 
*     KHAIDN(3,I) - Proton tag
*     KHAIDN(4,I) - Heavy  tag
*                  -1 - no information available
*                   0 - not a      pion/kaon/proton/heavy
*                   1 - loose      pion/kaon/proton/heavy
*                   2 - standard   pion/kaon/proton/heavy
*                   3 - tight      pion/kaon/proton/heavy
*
*     KHAIDT(1,I) - Pion   track selection
*     KHAIDT(2,I) - Kaon   track selection
*     KHAIDT(3,I) - Proton track selection
*     KHAIDT(4,I) - Heavy  track selection
*                  -1 - no information available
*                   0 - very loose pion/kaon/proton/heavy
*                   1 - loose      pion/kaon/proton/heavy
*                   2 - standard   pion/kaon/proton/heavy
*                   3 - tight      pion/kaon/proton/heavy
*/
    inline const int LNHADN = 4;
    extern "C" struct
    {
        int nhaidn;
        int khaidn[MTRACK][LNHADN];
        int khaidt[MTRACK][LNHADN];
    } pschdn_;

    inline int &NHAIDN = pschdn_.nhaidn;
    inline int &KHAIDN(int i, int j) { return pschdn_.khaidn[j - 1][i - 1]; }
    inline int &KHAIDT(int i, int j) { return pschdn_.khaidt[j - 1][i - 1]; }
    
} // namespace skelana

#endif // SKELANA_PSCHDN_HPP
