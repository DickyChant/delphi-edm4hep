#ifndef SKELANA_PSCFLG_HPP
#define SKELANA_PSCFLG_HPP

namespace skelana
{
/* +KEEP,PSCFLG.                         Control flags and keys
*
*     Flags to fill the COMMONs: 0 - do NOT fill the commons
*                                1 - filling from  the tapes
*                                2 - filling trough packages
*
*      flag    fill the COMMON's with        values  default
*     ------   ----------------------        ------  -------
*     IFLTRA - Track      Information        0 1        1
*              0 - COMMOM not filled
*              1 - COMMON filled
*
*     IFLODR - Re-order tracks               0 1        1
*              0 - order of DST PAs (DO NOT USE WITH OLD CODES!)
*              1 - chged then neutral
*     
*     IFLVEC - VECP vector filling           0 -22      22
*              0 - no VECP vector filling
*              1 - fill all tracks except the "new incoming" ones 
*                    and PAs in REMCLU clusters
*             11 - fill all tracks,  lock the "new incoming" ones 
*              2 - fill all tracks except the "charged outgoing" ones 
*                    and PAs in REMCLU clusters
*             22 - fill all tracks,  lock the "charged outgoing" ones
*              3 - fill all tracks except the "charged outgoing" ones
*                    and ignore the REMCLU PAs, using the old original ones
*                    if ISVER.LT.108 is set equivalent to IFLVEC = 2
*
*     IFLSTR - Track selection :             0 -11      11
*              0 - no selection applied
*              1 - track selection applied , rejected tracks removed
*             11 - track selection applied , rejected tracks flagged
*                    in LVLOCK,LVSELE
*
*     IFLCUT - Track selection tuning        0 - 3      3      
*              1 - Old SKELANA selection
*              2 - May 98 tuning for 97 data
*              3 - April 99 tuning for 98 data (SKELANA/XSDST 1.07)
*
*     IFLRVR - Recovery routine              0-111        111
*              0 - recovery routine not applied
*             >0 - routine applied, overwrites VECP, TRAC bank  
*            ..1 - high momentum track refit with PV constraint
*            .1. - mammoth recovery
*            1.. - recover charged tracks as neutrals
* (e.g. 111- run all three, 011 - don't use netral recovery)
*              
*     IFLSIM - Simulation Information        0 1        1
*              0 - COMMOM not filled
*              1 - COMMON filled
*
*     IFLBSP - Beam Spot  Information        0 1 2      2
*              0 - COMMON not filled
*              1 - Filled from DST bank
*              2 - Read from Beamspot file
*
*     IFLBTG - B tagging  Information        0 1 2      2
*              0 - COMMON not filled
*              1 - Filled from XDST bank, or recalculate for FullDST
*              2 - recalculate with AABTAG
*
*     IFLPVT - Primary vertex treatment      0 - 1      1
*              0 - DELANA primary vertex
*              1 - Btagging primary vertex (if b-tagging used)
*    
*     IFLVDR - refit VD with Z tracks with PV constraint 0-1 1
*              0 - Inactive
*              1 - Active
*
*     IFLFCT - refit FCA/FCB (RIF)  with PV constraint 0-1 1
*              0 - Inactive
*              1 - Active
*
*     IFLRNQ - Run quality selection         0 1        0 
*              0 - Inactive
*              1 - Read Runquality file and apply selection
*
*     IFLBHP - Skip the bad 1997 HPC events  0 1        1
*              0 - Yes
*              1 - No
*
*     IFLUTE - Unassociated TE banks           0 1        1
*              0 - COMMON not filled
*              1 - COMMON filled
*
*     IFLVDH - Vertex     Detector hits      0 1        1
*              0 - COMMON not filled
*              1 - COMMON filled
*
*     IFLMUO - Muon       Identification     0 1        1
*              0 - COMMON not filled
*              1 - COMMON filled for XSDST
*
*     IFLECL - Electromagnetic cluster Information      0 -22      2
*              0 - no REMCLU
*              1 - from the DST, fill VECP with clusters
*              2 - rerun, fill VECP with clusters
*             11 - from the DST, fill PSCECL COMMON only
*             22 - rerun, fill PSCECL COMMON only
*
*     IFLELE - ELEPHANT Electron Identification     0 1        1
*              0 - COMMON not filled
*              1 - COMMON filled
*
*     IFLEMC - Electromagnetic Calorimetry        0 1        1
*              0 - COMMON not filled
*              1 - COMMON filled
*
*     IFLPHO - Photon     Identification     0 1        1
*              0 - COMMON not filled
*              1 - COMMON filled
*
*     IFLPHC - Photon     Conversion         0 1        1
*              0 - COMMON not filled
*              1 - COMMON filled for XSDST
*
*     IFLSTC - STIC information              0 1        1
*              0 - COMMON not filled
*              1 - COMMON filled for XSDST
*
*     IFLHAC - Hadron     Calorimetry        0 1        1
*              0 - COMMON not filled
*              1 - COMMON filled
*
*     IFLHAD - Hadron     Identification     0 1        1
*              0 - COMMON not filled
*              1 - COMMON filled
*
*     IFLRV0 - V0         Reconstruction     0 1        1
*              0 - COMMON not filled
*              1 - COMMON filled for XShortDST
*
*     IFLJET - Jet reconstruction algorithm  0 - 3      0
*              0 - no reconstruction
*              1 - LUCLUS (standard)
*              2 - JADE  scaled inv. mass
*              3 - JADE  fixed  inv. mass
*/

    extern "C" struct
    {
        int ifltra;
        int iflfix;
        int iflrnq;
        int iflstr;
        int ifljet;
        int iflsim;
        int iflbsp;
        int iflbtg;
        int iflemc;
        int iflhac;
        int iflstc;
        int iflele;
        int iflpho;
        int iflmuo;
        int iflhad;
        int iflvdh;
        int iflrv0;
        int iflute;
        int iflphc;
        int iflvec;
        int iflbhp;
        int iflecl;
        int iflrvr;
        int iflodr;
        int iflpvt;
        int iflcut;
        int iflvdr;
        int iflfct;
        int iflenr;
    } pscflg_;

    inline int &IFLTRA = pscflg_.ifltra;
    inline int &IFLFIX = pscflg_.iflfix;
    inline int &IFLRNQ = pscflg_.iflrnq;
    inline int &IFLSTR = pscflg_.iflstr;
    inline int &IFLJET = pscflg_.ifljet;
    inline int &IFLSIM = pscflg_.iflsim;
    inline int &IFLBSP = pscflg_.iflbsp;
    inline int &IFLBTG = pscflg_.iflbtg;
    inline int &IFLEMC = pscflg_.iflemc;
    inline int &IFLHAC = pscflg_.iflhac;
    inline int &IFLSTC = pscflg_.iflstc;
    inline int &IFLELE = pscflg_.iflele;
    inline int &IFLPHO = pscflg_.iflpho;
    inline int &IFLMUO = pscflg_.iflmuo;
    inline int &IFLHAD = pscflg_.iflhad;
    inline int &IFLVDH = pscflg_.iflvdh;
    inline int &IFLRV0 = pscflg_.iflrv0;
    inline int &IFLUTE = pscflg_.iflute;
    inline int &IFLPHC = pscflg_.iflphc;
    inline int &IFLVEC = pscflg_.iflvec;
    inline int &IFLBHP = pscflg_.iflbhp;
    inline int &IFLECL = pscflg_.iflecl;
    inline int &IFLRVR = pscflg_.iflrvr;
    inline int &IFLODR = pscflg_.iflodr;
    inline int &IFLPVT = pscflg_.iflpvt;
    inline int &IFLCUT = pscflg_.iflcut;
    inline int &IFLVDR = pscflg_.iflvdr;
    inline int &IFLFCT = pscflg_.iflfct;
    inline int &IFLENR = pscflg_.iflenr;

}

#endif // SKELANA_PSCFLG_HPP