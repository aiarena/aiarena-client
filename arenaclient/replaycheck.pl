#!/usr/bin/perl
use strict;
use warnings;

chomp(my $replay = $ARGV[0]);
system("/home/aiarena/aiarena-client/sc2replayparser -gameevts -outfile replay.json $replay");
my $gameeventserr = `grep '"GameEvtsErr": true,' replay.json`;
if ($gameeventserr) {
        unlink($replay);
}