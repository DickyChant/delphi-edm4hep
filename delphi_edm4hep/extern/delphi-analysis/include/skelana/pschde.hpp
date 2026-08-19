#ifndef SKELANA_PSCHDE_HPP
#define SKELANA_PSCHDE_HPP

#include "skelana/mtrack.hpp"

namespace skelana
{
/*                             Hadron identification based on
*                             dE/dx in TPC using probabilities
*     KHAIDE(1,I) - Pion   tag
*     KHAIDE(2,I) - Kaon   tag 
*     KHAIDE(3,I) - Proton tag
*     KHAIDE(4,I) - Heavy  tag
*     KHAIDE(5,I) - Electron  tag
*                  -1 - no information available
*                   0 - not a    pion/kaon/proton/heavy/electron
*                   1 - loose    pion/kaon/proton/heavy/electron
*                   2 - standard pion/kaon/proton/heavy/electron
*                   3 - tight    pion/kaon/proton/heavy/electron
*     KHAIDE(6,I) - Selection flag
*                  -1 - no information available
*                   1 - more than 30 wires in  TPC  and
*                       within 2.5 s.d. of a hypothesis

*/
    inline const int LNHADE = 6;
    extern "C" struct
    {
        int nhaide;
        int khaide[MTRACK][LNHADE];
    } pschde_;

    inline const int &NHAIDE = pschde_.nhaide;
    inline const int &KHAIDE(int i, int j) { return pschde_.khaide[j-1][i-1]; };

} // namespace skelana

#endif // SKELANA_PSCHDE_HPP