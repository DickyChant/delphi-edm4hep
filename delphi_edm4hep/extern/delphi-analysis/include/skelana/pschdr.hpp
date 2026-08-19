#ifndef SKELANA_PSCHDR_HPP
#define SKELANA_PSCHDR_HPP

#include "skelana/mtrack.hpp"

namespace skelana
{
/*                            Hadron identification based on
*                             RICH gas/liquid, RIBMEAN probabilities,
*                             no tracking requirements
*
*     NHAIDR                - Number of identified hadrons
*     LNHADR                - Length of the had. id. information
*     QHAIDR(LNHADR,MTRACK) - Real    array of HAIDR information
*     KHAIDR(LNHADR,MTRACK) - Integer array of HAIDR information
*
*     KHAIDR(1,I) - Pion      tag
*     KHAIDR(2,I) - Kaon      tag 
*     KHAIDR(3,I) - Proton    tag
*     KHAIDR(4,I) - Heavy     tag
*     KHAIDR(5,I) - Electron  tag
*                  -1 - no information available
*                   0 - not a    pion/kaon/proton/heavy/electron
*                   1 - loose    pion/kaon/proton/heavy/electron
*                   2 - standard pion/kaon/proton/heavy/electron
*                   3 - tight    pion/kaon/proton/heavy/electron
*     KHAIDR(6,I) - Selection flag
*                  -1 - no information available
*                   bit 1 - liquid O.K.
*                   bit 2 - gas    O.K.
*/    
    inline const int LNHDR = 6;
    extern "C" struct
    {
        int nhaidr;
        int khaidr[MTRACK][LNHDR];
    } pschdr_;

    inline const int &NHAIDR = pschdr_.nhaidr;
    inline const int &KHAIDR(int i, int j) { return pschdr_.khaidr[j-1][i-1]; };
}

#endif // SKELANA_PSCHDR_HPP